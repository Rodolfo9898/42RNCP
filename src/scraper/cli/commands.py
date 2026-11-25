"""Command pattern: every mode of the program is an object with one method, execute()."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from scraper.site.login import SessionManager
from scraper.plan.catalog import Catalog
from scraper.core.config import Settings
from scraper.core.debug import PageDumper
from scraper.inventory.report import PlanReport
from scraper.storage.download import FileDownloader, ProjectSaver
from scraper.core.exceptions import ScraperError, SessionExpired
from scraper.site.gateway import FileCollector, ProjectReader
from scraper.storage.library import Library
from scraper.core.models import Stats
from scraper.site.page import PageParser
from scraper.core.reporting import Reporter
from scraper.plan.tracks import Plan, Target
from scraper.core.utils import first_line, human_size


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
    """--dry-run: what is in the library and what is missing, per track, as text. The numbers come from a PlanReport."""

    def __init__(self, report: PlanReport, library: Library, reporter: Reporter) -> None:
        self.report, self.library, self.reporter = report, library, reporter

    def execute(self) -> None:
        log, report = self.reporter.log, self.report
        for track in report.tracks:
            log(f"\n{track.track}: {track.total} project(s), {track.with_pdf} with a PDF, {len(track.missing)} missing")
            for m in track.missing:
                log(f"  + {self.library.shown(self.library.samples / m.path)}   ({m.slug})")
            for name in track.unknown:
                log(f"  ? {name}: not in the catalog (data/projects_21.json)")
        if report.artifacts:
            log(f"\nartifacts: {report.artifacts.checked} project(s) already checked, {report.artifacts.to_visit} to visit "
                f"(they go to {self.library.artifacts.name}/[<group>/]<name>/)")
        if report.misplaced:
            log(f"\n{report.misplaced} PDF(s) or artifact folder(s) are not in the folder of their series: "
                "`make samples ARGS=--reorganize` files them (add --dry-run to see the moves first).")
        log(f"\n{report.to_visit} project page(s) would be visited. Nothing was downloaded (dry run).")
        if report.unassigned is not None:
            log(f"\n{len(report.unassigned)} 42cursus project(s) of the catalog are in no track (add the ones you want to data/post-common-core.txt):")
            for slug in report.unassigned:
                log(f"  {slug}")


def never_cancelled() -> bool:
    return False


class ScrapeCommand(Command):
    """The main job: for each project that needs it, read its page and download the subject and the artifacts.

    `cancelled` is asked between two projects (the downloader service passes the stop flag of its job); `stats` is what the run did."""

    def __init__(self, *, targets: list[Target], settings: Settings, session: SessionManager, library: Library, reporter: Reporter,
                 dumper: PageDumper, force: bool = False, cancelled: Callable[[], bool] = never_cancelled) -> None:
        self.targets, self.settings, self.session, self.library = targets, settings, session, library
        self.reporter, self.dumper, self.force, self.cancelled = reporter, dumper, force, cancelled
        self.stats = Stats()
        self.stopped = False        # True when the run ended because `cancelled` said so

    def execute(self) -> None:
        log = self.reporter.log
        todo = self.library.visits(self.targets, with_artifacts=self.settings.with_artifacts, force=self.force)
        log(f"{len(self.targets)} project(s) selected, {len(todo)} to visit.")
        if not todo:
            log("Nothing to do: every PDF is there" + (" and every page was checked for artifacts." if self.settings.with_artifacts else "."))
            return
        gateway = self.session.open()
        reader = ProjectReader(gateway, PageParser(), FileCollector(), self.reporter, self.dumper)
        saver = ProjectSaver(FileDownloader(gateway.http, self.reporter), self.library, self.settings, self.reporter)
        for i, target in enumerate(todo, 1):
            if self.cancelled():
                self.stopped = True
                log("Stopped on request.")
                return
            log(f"\n[{i}/{len(todo)}] {target.track}/{target.stem}  ({target.slug})")
            try:
                info = reader.read(target.slug, self.stats)
                if info is not None and saver.save(target, info, force=self.force, stats=self.stats):
                    self.library.mark_checked(target.stem)
            except SessionExpired:
                raise
            except Exception as exc:      # keep going on a single bad project
                log(f"  ! failed: {first_line(exc)}")
                self.stats.failed.append(target.stem)
            time.sleep(self.settings.delay)
        self._print_summary(self.stats)

    def _print_summary(self, stats: Stats) -> None:
        log, c = self.reporter.log, stats.counts
        log(f"\nDone: {c['subject']} subject(s) and {c['artifact']} artifact(s) downloaded, {c['existing']} already there.")
        log(f"PDFs are in {self.library.samples}, artifacts in {self.library.artifacts} ({human_size(sum(f.stat().st_size for t in self.targets for f in self.library.artifact_files(t)))}).")
        if stats.no_files:
            log(f"No files found for {len(stats.no_files)} project(s) (probably no access): " + ", ".join(stats.no_files))
        if stats.failed:
            log(f"{len(stats.failed)} failure(s), run it again to retry: " + ", ".join(stats.failed))
