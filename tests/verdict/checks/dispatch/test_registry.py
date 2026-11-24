"""The registry of checkers, and the run that applies them."""

import pytest

from verdict.checks import Ctx, run_checks
from verdict.checks.dispatch.registry import CheckerRegistry, default_registry
from verdict.checks.engine.checker import Audit, Checker, Phase
from verdict.checks.engine.manual import ManualChecker
from verdict.checks.engine.results import result
from verdict.core.models import Rule
from verdict.gateways.sandbox import SandboxError

from tests.verdict.checks.helpers import project

KINDS = ["required_files", "libft_copy", "makefile_rules", "language", "include_guards", "cpp_forbidden_calls", "cpp_forbidden_keywords",
         "cpp_no_stl", "bonus_rule", "manual", "readme", "program", "build_unit", "flags", "std98", "no_relink", "allowed_functions",
         "functions_defined", "norm", "no_globals", "no_crash", "no_leaks"]


def rule(kind, **more):
    return Rule(id=kind, kind=kind, title=f"{kind} rule", text=f"text of {kind}", **more)


class Boom(Checker):
    kind = "boom"

    def evaluate(self, ctx, rule, facts):
        raise ValueError("a bug in this check")
        yield


class NeedsSandbox(Checker):
    kind = "needs_sandbox"

    def evaluate(self, ctx, rule, facts):
        ctx.run(["true"])
        yield self.result(rule, "pass", "ran")


class Fine(Checker):
    kind = "fine"

    def evaluate(self, ctx, rule, facts):
        yield self.result(rule, "pass", "fine")


class Late(Fine):
    kind, phase = "late", Phase.RUNTIME


class Early(Fine):
    kind, phase = "early", Phase.BUILD


class Opening(Audit):
    def run(self, ctx):
        yield result(None, "pass", "before", title="opening")


class Closing(Opening):
    needs_sandbox = True


def results_of(tmp_path, rules, registry):
    out = []
    run_checks(Ctx(repo=project(tmp_path, "main.c").resolve(), rules=rules, sandbox=None, lang="c"), out.append, registry)
    return out


def test_every_kind_of_rule_the_subjects_produce_has_its_checker():
    registry = default_registry()
    for kind in KINDS:
        assert registry.for_kind(kind).kind == kind, kind


def test_a_kind_nobody_checks_is_listed_for_a_human_and_comes_first_in_the_order():
    registry = default_registry()
    assert isinstance(registry.for_kind("something new"), ManualChecker)
    assert registry.phase_of("something new") == Phase.STATIC


def test_the_phases_run_from_reading_the_files_to_running_the_program():
    registry = default_registry()
    phases = [registry.phase_of(kind) for kind in ("language", "program", "norm", "no_crash")]
    assert phases == [Phase.STATIC, Phase.BUILD, Phase.ANALYSIS, Phase.RUNTIME] and phases == sorted(phases)


def test_rules_are_checked_phase_by_phase_whatever_their_order_in_the_subject(tmp_path):
    registry = CheckerRegistry([Fine(), Early(), Late()], fallback=ManualChecker())
    out = results_of(tmp_path, [rule("late"), rule("early"), rule("fine")], registry)
    assert [r.rule_id for r in out] == ["fine", "early", "late"]


def test_a_bug_in_one_check_does_not_abort_the_review(tmp_path):
    registry = CheckerRegistry([Fine(), Boom()], fallback=ManualChecker())
    out = results_of(tmp_path, [rule("boom"), rule("fine")], registry)
    assert [(r.rule_id, r.status) for r in out] == [("boom", "warn"), ("fine", "pass")]
    assert "The check itself crashed: ValueError: a bug in this check" in out[0].detail and out[0].title == "boom rule"


def test_a_rule_that_needs_the_sandbox_is_skipped_when_there_is_none(tmp_path):
    registry = CheckerRegistry([NeedsSandbox()], fallback=ManualChecker())
    out = results_of(tmp_path, [rule("needs_sandbox")], registry)
    assert [(r.status, r.detail) for r in out] == [("skipped", "Needs the sandbox: no sandbox configured")]
    with pytest.raises(SandboxError):
        Ctx(repo=tmp_path, rules=[], sandbox=None).run(["true"])


def test_a_kind_nobody_checks_is_emitted_as_manual_with_the_text_of_the_rule(tmp_path):
    out = results_of(tmp_path, [rule("something new")], CheckerRegistry([], fallback=ManualChecker()))
    assert [(r.status, r.detail, r.auto) for r in out] == [("manual", "text of something new", False)]


def test_audits_run_around_the_rules_and_those_that_need_the_sandbox_are_left_out_without_one(tmp_path):
    registry = CheckerRegistry([Fine()], fallback=ManualChecker(), opening=[Opening()], closing=[Closing()])
    out = results_of(tmp_path, [rule("fine")], registry)
    assert [r.title for r in out] == ["opening", "fine rule"]                    # no sandbox: the closing audit does not run
