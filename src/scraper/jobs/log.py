"""The log of a download: written by the thread that runs it, read by whoever asks how it is going."""
from __future__ import annotations

import threading

from scraper.core.reporting import Reporter


class LogReporter(Reporter):
    """A Reporter that keeps what it is told, line by line, so that a reader can ask for the lines from the one it already has."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._lock = threading.Lock()

    def log(self, message: str = "") -> None:
        with self._lock:
            self._lines.extend(message.split("\n"))        # a message is as many lines as print() would have made of it

    def since(self, start: int) -> tuple[list[str], int]:
        """The lines from index `start` on, and the index to ask for next time (the number of lines so far)."""
        with self._lock:
            return self._lines[start:], len(self._lines)
