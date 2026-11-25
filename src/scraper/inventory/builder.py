"""Counting what the library holds against the plan. Offline: nothing is fetched."""
from __future__ import annotations

from collections.abc import Sequence

from scraper.core.config import Settings
from scraper.inventory.report import ArtifactsReport, MissingSubject, PlanReport, TrackReport
from scraper.plan.catalog import Catalog
from scraper.plan.target import Target
from scraper.plan.tracks import TRACK_LABELS, TRACKS, Plan
from scraper.storage.library import Library
from scraper.storage.reorganize import Reorganizer


class PlanReportBuilder:
    """Builder of the PlanReport of some targets: the one source of the numbers, whoever shows them."""

    def __init__(self, plan: Plan, catalog: Catalog, library: Library, settings: Settings) -> None:
        self.plan, self.catalog, self.library, self.settings = plan, catalog, library, settings

    def build(self, targets: Sequence[Target], *, unassigned: bool = False) -> PlanReport:
        tracks = [self._track(track, mine) for track in TRACKS if (mine := [t for t in targets if t.track == track])]
        return PlanReport(
            tracks=tuple(tracks),
            artifacts=self._artifacts(targets) if self.settings.with_artifacts else None,
            misplaced=len(Reorganizer(self.library).moves(targets)),
            to_visit=len(self.library.visits(targets, with_artifacts=self.settings.with_artifacts)),
            unassigned=self._unassigned() if unassigned else None,
        )

    def _track(self, track: str, mine: Sequence[Target]) -> TrackReport:
        missing = self.library.missing(mine)
        absent = tuple(MissingSubject(t.stem, self.library.pdf_path(t).relative_to(self.library.samples).as_posix(), t.slug) for t in missing)
        return TrackReport(track, TRACK_LABELS[track], len(mine), len(mine) - len(missing), absent, tuple(self.plan.unresolved.get(track, [])))

    def _artifacts(self, targets: Sequence[Target]) -> ArtifactsReport:
        checked = self.library.checked()
        todo = [t for t in targets if t.stem not in checked]
        return ArtifactsReport(len(targets) - len(todo), len(todo))

    def _unassigned(self) -> tuple[str, ...]:
        taken = {t.project.id for t in self.plan.targets}
        return tuple(p.slug for p in self.catalog.projects
                     if p.id not in taken and p.slug.startswith("42cursus-") and not p.name.lower().startswith("exam"))
