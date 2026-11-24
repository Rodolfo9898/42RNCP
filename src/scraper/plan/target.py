"""One project to keep: its track, the project, and the folder of the series it belongs to."""
from __future__ import annotations

from dataclasses import dataclass

from scraper.plan.catalog import Project
from scraper.plan.names import stem


@dataclass(frozen=True)
class Target:
    track: str
    project: Project
    parent: Project | None = None
    group: str = ""                  # the folder of its series (cpp-modules, piscine-django...), "" for a project on its own

    @property
    def stem(self) -> str:
        return stem(self.project.slug)

    @property
    def slug(self) -> str:
        return self.project.slug

    @property
    def folders(self) -> tuple[str, ...]:
        """Where it sits below its track: (group,) or nothing."""
        return (self.group,) if self.group else ()
