"""Stand-ins for the jobs tests: a command that does what the test says, in the shape ScrapeCommand has for the job."""
from __future__ import annotations

import threading
from collections.abc import Callable

from scraper.core.models import Stats
from scraper.core.reporting import Reporter


class FakeCommand:
    """Logs some lines, then does `then` (raise something, say). `stopped` is what ScrapeCommand sets when it saw the stop request.
    `hold`: it waits, once started, until the test sets `release` (to ask for a stop while it runs in a thread, without any sleep)."""

    def __init__(self, reporter: Reporter, cancelled: Callable[[], bool], *, lines: tuple[str, ...] = (), then: Callable[[], None] = lambda: None,
                 downloaded: int = 0, failed: tuple[str, ...] = (), stops: bool = False, hold: bool = False) -> None:
        self.reporter, self.cancelled, self.lines, self.then, self.stops, self.hold = reporter, cancelled, lines, then, stops, hold
        self.stats = Stats()
        self.stats.counts["subject"] += downloaded
        self.stats.failed.extend(failed)
        self.stopped = False
        self.started, self.release = threading.Event(), threading.Event()
        self.thread: threading.Thread | None = None

    def execute(self) -> None:
        self.thread = threading.current_thread()
        self.started.set()
        if self.hold:
            assert self.release.wait(timeout=10)
        for line in self.lines:
            self.reporter.log(line)
        self.then()
        self.stopped = self.stops and self.cancelled()


def command_of(**kwargs) -> Callable[[Reporter, Callable[[], bool]], FakeCommand]:
    """A CommandFactory for a FakeCommand; the command it makes is kept in `.made`."""
    def make(reporter, cancelled):
        make.made = FakeCommand(reporter, cancelled, **kwargs)
        return make.made
    return make


def raising(error: BaseException) -> Callable[[], None]:
    def fail() -> None:
        raise error
    return fail
