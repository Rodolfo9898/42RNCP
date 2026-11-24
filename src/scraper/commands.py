"""Command pattern: every mode of the program is an object with one method, execute()."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from .auth import SessionManager
from .catalog import Catalog
from .config import Settings
from .debug import PageDumper
from .download import FileDownloader, ProjectSaver
from .exceptions import ScraperError, SessionExpired
from .intra import FileCollector, ProjectReader
from .library import Library
from .models import Stats
from .page import PageParser
from .reporting import Reporter
from .tracks import TRACKS, Plan, Target
from .utils import first_line, human_size


class Command(ABC):
    @abstractmethod
    def execute(self) -> None:
        ...


def select_targets(plan: Plan, catalog: Catalog, *, tracks: list[str] | None, projects: list[str] | None) -> list[Target]:
    """The plan narrowed down by --track and --project (a slug, a name, an id or a stem)."""
    targets = [t for t in plan.targets if not tracks or t.track in tracks]
    if projects:
        chosen: list[Target] = []
        for token in projects:
            found = catalog.resolve(token)
            match = next((t for t in plan.targets if (found and t.project.id == found.id) or token in (t.stem, t.slug)), None)
            if match is None:
                hint = ("it is in the catalog but in no track: add it to scraper/data/post-common-core.txt (or common-core.txt)"
                        if found else "the catalog does not know it")
                raise ScraperError(f"{token!r} is not in the plan: {hint}.")
            if match in targets and match not in chosen:
                chosen.append(match)
        targets = chosen
    return targets


class PlanCommand(Command):
    """--dry-run: what is in the library and what is missing, per track. Offline: nothing is fetched."""

    def __init__(self, targets: list[Target], plan: Plan, catalog: Catalog, library: Library, settings: Settings,
                 reporter: Reporter, *, unassigned: bool = False) -> None:
        self.targets, self.plan, self.catalog, self.library = targets, plan, catalog, library
        self.settings, self.reporter, self.unassigned = settings, reporter, unassigned

    def execute(self) -> None:
        log = self.reporter.log
        checked = self.library.checked()
        for track in TRACKS:
            mine = [t for t in self.targets if t.track == track]
            if not mine:
                continue
            missing = [t for t in mine if not self.library.find_pdf(t.stem)]
            log(f"\n{track}: {len(mine)} project(s), {len(mine) - len(missing)} with a PDF, {len(missing)} missing")
            for t in missing:
                log(f"  + samples/{track}/{t.stem}.pdf   ({t.slug})")
            for name in self.plan.unresolved.get(track, []):
                log(f"  ? {name}: not in the catalog (data/projects_21.json)")
        if self.settings.with_artifacts:
            todo = [t for t in self.targets if t.stem not in checked]
            log(f"\nartifacts: {len(self.targets) - len(todo)} project(s) already checked, {len(todo)} to visit "
                f"(they go to {self.library.artifacts.name}/<name>/)")
        visits = [t for t in self.targets if _needs_visit(t, self.library, self.settings, force=False)]
        log(f"\n{len(visits)} project page(s) would be visited. Nothing was downloaded (dry run).")
        if self.unassigned:
            taken = {t.project.id for t in self.plan.targets}
            rest = [p for p in self.catalog.projects if p.id not in taken and p.slug.startswith(("42cursus-",)) and not p.name.lower().startswith("exam")]
            log(f"\n{len(rest)} 42cursus project(s) of the catalog are in no track (add the ones you want to data/post-common-core.txt):")
            for p in rest:
                log(f"  {p.slug}")


def _needs_visit(target: Target, library: Library, settings: Settings, *, force: bool) -> bool:
    """A page is read when the PDF is missing or, if the artifacts are wanted, when it has not been read in full yet."""
    if force or library.find_pdf(target.stem) is None:
        return True
    return settings.with_artifacts and target.stem not in library.checked()


class ScrapeCommand(Command):
    """The main job: for each project that needs it, read its page and download the subject and the artifacts."""

    def __init__(self, *, targets: list[Target], settings: Settings, session: SessionManager, library: Library, reporter: Reporter,
                 dumper: PageDumper, force: bool = False) -> None:
        self.targets, self.settings, self.session, self.library = targets, settings, session, library
        self.reporter, self.dumper, self.force = reporter, dumper, force

    def execute(self) -> None:
        log = self.reporter.log
        todo = [t for t in self.targets if _needs_visit(t, self.library, self.settings, force=self.force)]
        log(f"{len(self.targets)} project(s) selected, {len(todo)} to visit.")
        if not todo:
            log("Nothing to do: every PDF is there" + (" and every page was checked for artifacts." if self.settings.with_artifacts else "."))
            return
        gateway = self.session.open()
        reader = ProjectReader(gateway, PageParser(), FileCollector(), self.reporter, self.dumper)
        saver = ProjectSaver(FileDownloader(gateway.http, self.reporter), self.library, self.settings, self.reporter)
        stats = Stats()
        for i, target in enumerate(todo, 1):
            log(f"\n[{i}/{len(todo)}] {target.track}/{target.stem}  ({target.slug})")
            try:
                info = reader.read(target.slug, stats)
                if info is not None and saver.save(target, info, force=self.force, stats=stats):
                    self.library.mark_checked(target.stem)
            except SessionExpired:
                raise
            except Exception as exc:      # keep going on a single bad project
                log(f"  ! failed: {first_line(exc)}")
                stats.failed.append(target.stem)
            time.sleep(self.settings.delay)
        self._print_summary(stats)

    def _print_summary(self, stats: Stats) -> None:
        log, c = self.reporter.log, stats.counts
        log(f"\nDone: {c['subject']} subject(s) and {c['artifact']} artifact(s) downloaded, {c['existing']} already there.")
        log(f"PDFs are in {self.library.samples}, artifacts in {self.library.artifacts} ({human_size(sum(f.stat().st_size for t in self.targets for f in self.library.artifact_files(t.stem)))}).")
        if stats.no_files:
            log(f"No files found for {len(stats.no_files)} project(s) (probably no access): " + ", ".join(stats.no_files))
        if stats.failed:
            log(f"{len(stats.failed)} failure(s), run it again to retry: " + ", ".join(stats.failed))
