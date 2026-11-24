"""Where messages go. Classes receive a Reporter instead of calling print(), so tests can capture them."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Reporter(ABC):
    @abstractmethod
    def log(self, message: str = "") -> None:
        ...


class ConsoleReporter(Reporter):
    def log(self, message: str = "") -> None:
        print(message, flush=True)
