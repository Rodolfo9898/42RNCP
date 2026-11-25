"""What a download did, in numbers."""
from __future__ import annotations

from dataclasses import dataclass

from scraper.core.models import Stats


@dataclass(frozen=True)
class DownloadSummary:
    downloaded_subjects: int
    downloaded_artifacts: int
    existing: int
    failed: tuple[str, ...]
    no_files: tuple[str, ...]

    @classmethod
    def of(cls, stats: Stats) -> DownloadSummary:
        counts = stats.counts
        return cls(counts["subject"], counts["artifact"], counts["existing"], tuple(stats.failed), tuple(stats.no_files))

    @property
    def empty(self) -> bool:
        """Nothing was downloaded, found there already or went wrong."""
        return not (self.downloaded_subjects or self.downloaded_artifacts or self.existing or self.failed or self.no_files)
