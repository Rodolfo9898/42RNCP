"""The base class: the steps of a check run in a fixed order, and a subclass fills only the ones it needs."""

from verdict.checks import Ctx
from verdict.checks.context.memo import memo
from verdict.checks.engine.checker import Checker
from verdict.checks.engine.results import label, result, tail
from verdict.core.models import Rule, Source


class Recording(Checker):
    kind = "recording"

    def __init__(self, skipped=False):
        self.steps, self.skipped = [], skipped

    def skip(self, ctx, rule):
        self.steps.append("skip")
        return self.result(rule, "na", "does not apply") if self.skipped else None

    def prepare(self, ctx, rule):
        self.steps.append("prepare")
        return {"facts": 1}

    def evaluate(self, ctx, rule, facts):
        self.steps.append(f"evaluate {facts}")
        yield self.result(rule, "pass", "fine")
        yield self.result(rule, "warn", "but", title="own title")

    def title(self, rule):
        return label(rule)


def rule(**more):
    return Rule(id="r", kind="recording", title="A rule", section="bonus", sources=[Source(pdf="x.pdf", page=2)], **more)


def ctx(tmp_path):
    return Ctx(repo=tmp_path, rules=[], sandbox=None)


def test_the_steps_run_in_order_and_the_facts_go_to_the_verdict(tmp_path):
    checker = Recording()
    results = list(checker.run(ctx(tmp_path), rule(unit="ex00")))
    assert checker.steps == ["skip", "prepare", "evaluate {'facts': 1}"]
    assert [(r.status, r.title) for r in results] == [("pass", "ex00: A rule"), ("warn", "own title")]
    assert results[0].rule_id == "r" and results[0].section == "bonus" and results[0].sources[0].page == 2


def test_a_check_that_does_not_apply_answers_before_looking_at_anything(tmp_path):
    checker = Recording(skipped=True)
    assert [r.status for r in checker.run(ctx(tmp_path), rule())] == ["na"] and checker.steps == ["skip"]


def test_a_result_keeps_the_end_of_a_long_log_and_is_automatic_unless_said_otherwise():
    long = result(rule(), "fail", "x", log="a" * 7000 + "end")
    assert len(long.log) == 6000 and long.log.endswith("end") and long.auto
    assert result(None, "pass").title == "Check" and not result(rule(), "manual", auto=False).auto


def test_the_end_of_an_output_is_its_last_lines():
    assert tail("1\n2\n3\n4\n", 2) == "3\n4"


def test_a_value_is_computed_once_per_cache():
    cache, calls = {}, []
    assert memo(cache, "k", lambda: calls.append(1) or "v") == "v" and memo(cache, "k", lambda: calls.append(1) or "w") == "v"
    assert calls == [1] and cache == {"k": "v"}
