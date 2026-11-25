"""Running downloads in the background, one at a time."""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

from scraper.jobs.job import CommandFactory, Download, DownloadJob, NoDownload
from scraper.jobs.state import JobSnapshot, JobState

Starter = Callable[[Callable[[], None]], None]          # how a job gets to run: the service uses a thread, a test can run it itself


class AlreadyRunning(Exception):
    """A download is running: the service does one at a time."""


def in_a_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="scraper-download", daemon=True).start()


def random_id() -> str:
    return uuid.uuid4().hex


class DownloadRunner:
    """Owns the current download: it starts the next one when none is running, and a finished one stays readable until then.
    How a job gets to run is a Strategy (`starter`): a thread in the service, the test's own hands in the tests."""

    def __init__(self, starter: Starter = in_a_thread, new_id: Callable[[], str] = random_id) -> None:
        self._starter, self._new_id = starter, new_id
        self._current: Download = NoDownload()
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._current.running

    def start(self, make_command: CommandFactory) -> DownloadJob:
        with self._lock:
            if self._current.running:
                raise AlreadyRunning("a download is already running: stop it or wait for it to finish")
            job = DownloadJob(self._new_id(), make_command)
            self._current = job
        self._starter(job.run)
        return job

    def cancel(self) -> JobState:
        return self._current.cancel()

    def snapshot(self, since: int = 0) -> JobSnapshot:
        return self._current.snapshot(since)
