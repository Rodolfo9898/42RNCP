"""What a download is at a given moment, as plain data."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from scraper.jobs.summary import DownloadSummary


class JobState(StrEnum):
    """idle: no download since the service started; running -> done | failed | cancelled."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class JobSnapshot:
    state: JobState
    id: str
    lines: list[str]
    next: int                            # the index to ask for next time
    summary: DownloadSummary | None
