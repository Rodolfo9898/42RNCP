"""What the library holds against the plan, as plain data: one object that the command line prints (`--dry-run`) and the service serialises."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MissingSubject:
    name: str            # the name on disk, without the extension (cpp00)
    path: str            # where its PDF goes, from the samples folder (common-core/cpp-modules/cpp00.pdf)
    slug: str            # the project's address on the intra


@dataclass(frozen=True)
class TrackReport:
    track: str
    label: str
    total: int
    with_pdf: int
    missing: tuple[MissingSubject, ...]
    unknown: tuple[str, ...]            # what the track's list names but the catalog does not know


@dataclass(frozen=True)
class ArtifactsReport:
    checked: int         # projects whose page was already read in full
    to_visit: int


@dataclass(frozen=True)
class PlanReport:
    tracks: tuple[TrackReport, ...]
    artifacts: ArtifactsReport | None         # None when the artifacts are not wanted
    misplaced: int                            # PDFs and artifact folders that are not in the folder of their series
    to_visit: int                             # project pages a download would read
    unassigned: tuple[str, ...] | None = None   # slugs of the catalog's 42cursus projects in no track (None: not asked for)

    @property
    def unknown(self) -> list[str]:
        return [name for track in self.tracks for name in track.unknown]
