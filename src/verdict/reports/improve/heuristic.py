"""What every heuristic of the improvement suggestions shares."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from verdict.checks import Ctx
from verdict.core.models import Evidence, Improvement


def evidence(file: Path | str, line: int | None = None, snippet: str = "") -> Evidence:
    return Evidence(file=str(file), line=line, snippet=snippet[:160])


class Heuristic(ABC):
    """Strategy: one way of reading the files for something worth improving. It never affects the verdict, and the logic findings
    are worded as "possible" because a script cannot prove a bug."""

    @abstractmethod
    def improvements(self, ctx: Ctx) -> Iterable[Improvement]: ...
