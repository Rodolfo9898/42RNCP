"""Putting the heuristics together into the list of suggestions."""

from __future__ import annotations

from collections.abc import Sequence

from verdict.checks import Ctx
from verdict.core.models import Improvement
from verdict.reports.improve.code import CodeHeuristic
from verdict.reports.improve.heuristic import Heuristic
from verdict.reports.improve.logic import LogicHeuristic
from verdict.reports.improve.structure import StructureHeuristic

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class Suggester:
    """Runs every heuristic over the project and lists what they found, most important first. A heuristic that breaks is
    reported as a finding of its own: it must not hide the others."""

    def __init__(self, heuristics: Sequence[Heuristic]) -> None:
        self.heuristics = list(heuristics)

    @classmethod
    def standard(cls) -> Suggester:
        return cls([StructureHeuristic(), CodeHeuristic(), LogicHeuristic()])

    def suggest(self, ctx: Ctx) -> list[Improvement]:
        out: list[Improvement] = []
        for heuristic in self.heuristics:
            try:
                out.extend(heuristic.improvements(ctx))
            except Exception as exc:  # one broken heuristic must not hide the others
                out.append(Improvement(category="code", priority="low", title=f"Analysis step {type(heuristic).__name__} failed",
                                       detail=f"{type(exc).__name__}: {exc}"))
        out.sort(key=lambda i: PRIORITY_ORDER[i.priority])
        return out


def suggest(ctx: Ctx) -> list[Improvement]:
    return Suggester.standard().suggest(ctx)
