"""What running one command in the environment under test gives back."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Outcome:
    rc: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


Runner = Callable[[list[str], Path, float], Outcome]
