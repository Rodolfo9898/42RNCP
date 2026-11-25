"""One download: the command that does it, its log, and the state it is in."""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable

import httpx

from scraper.cli.commands import ScrapeCommand
from scraper.core.exceptions import ScraperError, SessionExpired
from scraper.core.reporting import Reporter
from scraper.core.utils import first_line
from scraper.jobs.log import LogReporter
from scraper.jobs.state import JobSnapshot, JobState
from scraper.jobs.summary import DownloadSummary
from scraper.site.login import LOGIN_ON_YOUR_COMPUTER

# What a job needs to be built: the reporter that feeds its log and the question "was I asked to stop?" (the job owns both).
CommandFactory = Callable[[Reporter, Callable[[], bool]], ScrapeCommand]


class Download(ABC):
    """The download the service shows as the current one (Null Object: NoDownload stands in until the first one starts)."""

    @property
    @abstractmethod
    def running(self) -> bool:
        ...

    @abstractmethod
    def cancel(self) -> JobState:
        """Ask it to stop between two projects. The state it is in now (it only becomes cancelled when it has stopped)."""

    @abstractmethod
    def snapshot(self, since: int = 0) -> JobSnapshot:
        ...


class NoDownload(Download):
    """Null Object: the current download before the first one starts. Nothing to read, nothing to stop."""

    running = False

    def cancel(self) -> JobState:
        return JobState.IDLE

    def snapshot(self, since: int = 0) -> JobSnapshot:
        return JobSnapshot(JobState.IDLE, "", [], 0, None)


class DownloadJob(Download):
    """State machine: running, then done, failed (an error ended it) or cancelled (it was asked to stop). `run` is the whole life of
    the thread that executes it; the other methods are called from the requests."""

    def __init__(self, job_id: str, make_command: CommandFactory) -> None:
        self.id = job_id
        self.log = LogReporter()
        self._stop = threading.Event()
        self._command = make_command(self.log, self._stop.is_set)
        self._lock = threading.Lock()
        self._state, self._summary = JobState.RUNNING, None
        self.finished = threading.Event()           # set once the state is final

    @property
    def running(self) -> bool:
        return self.state is JobState.RUNNING

    @property
    def state(self) -> JobState:
        with self._lock:
            return self._state

    def cancel(self) -> JobState:
        self._stop.set()
        return self.state

    def snapshot(self, since: int = 0) -> JobSnapshot:
        with self._lock:                            # the state first: a final state means every line is already in the log
            state, summary = self._state, self._summary
        lines, following = self.log.since(since)
        return JobSnapshot(state, self.id, lines, following, summary)

    def run(self) -> None:
        try:
            self._command.execute()
            outcome = JobState.CANCELLED if self._command.stopped else JobState.DONE
        except SessionExpired as exc:
            self._fail(str(exc), f"The saved session stopped working: {LOGIN_ON_YOUR_COMPUTER}, then download again.")
            outcome = JobState.FAILED
        except ScraperError as exc:
            self._fail(str(exc))
            outcome = JobState.FAILED
        except httpx.HTTPError as exc:
            self._fail(f"Network error: {first_line(exc)}")
            outcome = JobState.FAILED
        except Exception as exc:                    # a thread must not die without a word: the log says what happened
            logging.exception("the download failed")
            self._fail(f"Unexpected error: {first_line(exc)}")
            outcome = JobState.FAILED
        self._settle(outcome)

    def _fail(self, *messages: str) -> None:
        for message in messages:
            self.log.log(message.strip())

    def _settle(self, outcome: JobState) -> None:
        summary = DownloadSummary.of(self._command.stats)
        with self._lock:
            self._summary = summary if outcome is JobState.DONE or not summary.empty else None
            self._state = outcome
        self.finished.set()
