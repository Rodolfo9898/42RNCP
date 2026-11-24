"""The state of a running review: who it reports to, how it is told to stop, and what it has cost."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Job:
    """What a running review reports to, and how it is told to stop."""

    notify: Callable[[str], None] = lambda _message: None
    cancel: threading.Event = field(default_factory=threading.Event)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage) -> None:
        self.input_tokens += (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        self.output_tokens += usage.output_tokens or 0
