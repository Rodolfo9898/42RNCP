from pathlib import Path

from verdict.checks import Ctx
from verdict.core.models import Improvement
from verdict.reports.improve import Heuristic, Suggester
from verdict.reports.improve.code import MAX_HITS, Line, LineRule


class Raises(Heuristic):
    def improvements(self, ctx):
        raise RuntimeError("the heuristic broke")
        yield  # (a generator, like the real ones)


class Says(Heuristic):
    def __init__(self, *improvements):
        self.found = improvements

    def improvements(self, ctx):
        yield from self.found


def ctx_for(repo: Path):
    return Ctx(repo=repo.resolve(), rules=[], sandbox=None, lang="c")


def test_a_heuristic_that_breaks_is_reported_and_does_not_hide_the_others(tmp_path):
    ok = Improvement(category="code", priority="high", title="Found")
    out = Suggester([Raises(), Says(ok)]).suggest(ctx_for(tmp_path))
    assert [i.title for i in out] == ["Found", "Analysis step Raises failed"]
    assert out[1].priority == "low" and out[1].detail == "RuntimeError: the heuristic broke"


def test_what_the_heuristics_found_is_listed_most_important_first(tmp_path):
    low, high = Improvement(category="code", priority="low", title="l"), Improvement(category="logic", priority="high", title="h")
    mid = Improvement(category="code", priority="medium", title="m")
    assert [i.title for i in Suggester([Says(low, mid), Says(high)]).suggest(ctx_for(tmp_path))] == ["h", "m", "l"]


def test_the_standard_suggester_has_the_three_readings():
    assert [type(h).__name__ for h in Suggester.standard().heuristics] == ["StructureHeuristic", "CodeHeuristic", "LogicHeuristic"]


def test_a_line_rule_keeps_only_the_first_few_hits():
    rule = LineRule(lambda line: line.raw.strip() if "x" in line.raw else None)
    for number in range(1, 40):
        rule.scan(Line(Path("a.c"), number, "x();" if number % 2 else "y();", "", "c"))
    assert len(rule.hits) == MAX_HITS == 10 and [h.line for h in rule.hits] == [1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
