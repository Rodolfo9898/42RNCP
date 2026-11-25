"""The projects and the files they are kept in, as the routes need them."""
from __future__ import annotations

from dataclasses import dataclass, replace

from scraper.cli.commands import select_targets
from scraper.core.config import Settings
from scraper.core.exceptions import ScraperError
from scraper.plan.catalog import Catalog
from scraper.plan.tracks import TRACKS, Plan, Target, build_plan
from scraper.storage.library import Library


@dataclass(frozen=True)
class Selection:
    """The projects a request is about, with the settings that go with them (children and artifacts are per request)."""

    settings: Settings
    plan: Plan
    targets: list[Target]


class Workspace:
    """Facade over the catalog (read once), the plan (built per request) and the library on disk."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = Catalog.load(settings.data_dir / "projects_21.json")
        self.library = Library(settings.samples_dir, settings.artifacts_dir)

    def select(self, *, tracks: list[str] | None = None, projects: list[str] | None = None, children: bool = True,
               artifacts: bool = True) -> Selection:
        """The targets of some tracks and/or projects (none given: all). A track or a project the plan does not have is a ScraperError."""
        unknown = [t for t in tracks or [] if t not in TRACKS]
        if unknown:
            raise ScraperError(f"unknown track {unknown[0]!r}: the tracks are {', '.join(TRACKS)}.")
        settings = replace(self.settings, with_children=children, with_artifacts=artifacts)
        plan = build_plan(self.catalog, settings.data_dir, with_children=children, with_experience=settings.with_experience)
        return Selection(settings, plan, select_targets(plan, self.catalog, tracks=tracks, projects=projects))
