"""Writing the subject and the artifacts of a project to disk."""
from __future__ import annotations

from pathlib import Path

import httpx

from scraper.core.config import Settings
from scraper.site.http import HttpClient
from scraper.storage.library import Library
from scraper.core.models import FileLink, ProjectInfo, Stats
from scraper.core.reporting import Reporter
from scraper.plan.tracks import Target
from scraper.core.utils import first_line, human_size, prune_empty


class FileDownloader:
    """Streams one URL to one file (via a .part file, so a failure never leaves a broken file)."""

    CHUNK = 1 << 16

    def __init__(self, http: HttpClient, reporter: Reporter) -> None:
        self.http, self.reporter = http, reporter

    def download(self, url: str, dest: Path, *, pdf: bool = False) -> int | None:
        """The size, or None on failure."""
        log = self.reporter.log
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        try:
            with self.http.stream(url) as response:
                if response.status_code >= 400:
                    log(f"  ! HTTP {response.status_code} for {url}")
                    return None
                if "text/html" in response.headers.get("Content-Type", "").lower() and dest.suffix.lower() not in (".html", ".htm"):
                    log(f"  ! {url} returned a web page instead of a file (session expired?), skipping")
                    return None
                chunks = response.iter_bytes(self.CHUNK)
                first = next(chunks, b"")
                if pdf and not first.startswith(b"%PDF"):
                    log(f"  ! {url} did not return a PDF, skipping")
                    return None
                with open(part, "wb") as fh:
                    fh.write(first)
                    for chunk in chunks:
                        fh.write(chunk)
            part.replace(dest)
            return dest.stat().st_size
        except httpx.HTTPError as exc:
            log(f"  ! download failed for {url}: {first_line(exc)}")
            return None
        finally:
            part.unlink(missing_ok=True)


def choose_subject(subjects: list[FileLink], lang: str) -> FileLink | None:
    """One PDF per project: the preferred language if the page has it, else the first."""
    return next((s for s in subjects if s.lang == lang), subjects[0] if subjects else None)


class ProjectSaver:
    """Saves one project: its subject as samples/<track>/<stem>.pdf and its other files in artifacts/<stem>/."""

    def __init__(self, downloader: FileDownloader, library: Library, settings: Settings, reporter: Reporter) -> None:
        self.downloader, self.library, self.settings, self.reporter = downloader, library, settings, reporter

    def _shown(self, path: Path) -> str:
        for base in (self.library.samples.parent, self.library.artifacts.parent):
            if path.is_relative_to(base):
                return path.relative_to(base).as_posix()
        return path.name

    def save(self, target: Target, info: ProjectInfo, *, force: bool, stats: Stats) -> bool:
        """True when nothing failed (so the project does not need to be visited again)."""
        failed_before = len(stats.failed)
        self._subject(target, info, force, stats)
        if self.settings.with_artifacts:
            self._artifacts(target, info, force, stats)
        return len(stats.failed) == failed_before

    def _subject(self, target: Target, info: ProjectInfo, force: bool, stats: Stats) -> None:
        existing = self.library.find_pdf(target.stem)
        if existing and not force:
            self.reporter.log(f"  = {self._shown(existing)} (exists)")
            stats.counts["existing"] += 1
            return
        link = choose_subject(info.subjects, self.settings.lang)
        if link is None:
            self.reporter.log("  ! no subject PDF on the page")
            stats.failed.append(f"{target.stem} (no subject PDF)")
            return
        self._save_file(link.url, existing or self.library.pdf_path(target.track, target.stem), pdf=True, force=force, stats=stats, kind="subject")

    def _artifacts(self, target: Target, info: ProjectInfo, force: bool, stats: Stats) -> None:
        folder = self.library.artifact_dir(target.stem)
        used: set[str] = set()
        for link in info.artifacts:
            name, n = link.filename, 2      # two different URLs can share a filename; keep the names stable across runs
            while name in used:
                name = f"{Path(link.filename).stem}_{n}{Path(link.filename).suffix}"
                n += 1
            used.add(name)
            self._save_file(link.url, folder / name, pdf=False, force=force, stats=stats, kind="artifact")
        prune_empty(folder, self.library.artifacts)      # a folder left empty by failed downloads is dropped

    def _save_file(self, url: str, dest: Path, *, pdf: bool, force: bool, stats: Stats, kind: str) -> None:
        if dest.exists() and not force:
            self.reporter.log(f"  = {self._shown(dest)} (exists)")
            stats.counts["existing"] += 1
            return
        size = self.downloader.download(url, dest, pdf=pdf)
        if size is None:
            stats.failed.append(self._shown(dest))
            return
        self.reporter.log(f"  + {self._shown(dest)} ({human_size(size)})")
        stats.counts[kind] += 1
