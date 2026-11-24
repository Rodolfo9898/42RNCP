"""The units that must build, and what the build produces."""

from __future__ import annotations

from collections.abc import Iterable

from verdict.checks.context.build_result import BuildResult
from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker, Phase
from verdict.checks.engine.results import label
from verdict.core.models import CheckResult, Rule


class BuiltUnitChecker(Checker):
    """A rule that is judged on the build of its unit (Template Method over Checker): the build runs once, a build that failed is
    answered the same way for all of them, and `judge_build` says what a build that worked has to show."""

    phase = Phase.BUILD

    def bonus(self, rule: Rule) -> bool:
        return False

    def prepare(self, ctx: Ctx, rule: Rule) -> BuildResult:
        return ctx.build(rule.unit, self.bonus(rule))

    def evaluate(self, ctx: Ctx, rule: Rule, build: BuildResult) -> Iterable[CheckResult]:
        if build.ok:
            yield from self.judge_build(ctx, rule, build)
        elif reason := ctx.offline_reason(build):    # not the project's fault, and not a pass either: someone must build it with a network
            yield self.result(rule, "warn", reason, log=build.log)
        else:
            yield self.result(rule, "fail", "The build failed." if build.ran else build.log, log=build.log)

    def judge_build(self, ctx: Ctx, rule: Rule, build: BuildResult) -> Iterable[CheckResult]:
        raise NotImplementedError


class ProgramChecker(BuiltUnitChecker):
    """`make` produces the program the subject names, and it is not empty."""

    kind = "program"

    def bonus(self, rule: Rule) -> bool:
        return bool(rule.params.get("bonus_target"))

    def title(self, rule: Rule) -> str:
        return label(rule, f"`make{' bonus' if self.bonus(rule) else ''}` builds `{rule.params['program']}`")

    def judge_build(self, ctx: Ctx, rule: Rule, build: BuildResult) -> Iterable[CheckResult]:
        name = rule.params["program"]
        path = ctx.unit_dir(rule.unit) / name
        if not path.is_file():
            yield self.result(rule, "fail", f"The build succeeded but `{name}` was not produced.", log=build.log)
        elif path.stat().st_size == 0:
            yield self.result(rule, "fail", f"`{name}` is empty.", log=build.log)
        else:
            yield self.result(rule, "pass", f"`{name}` was built.", log=build.log)


class BuildUnitChecker(BuiltUnitChecker):
    """A folder of the project (a C++ exercise) builds into something: a program or a library, not bare objects."""

    kind = "build_unit"

    def judge_build(self, ctx: Ctx, rule: Rule, build: BuildResult) -> Iterable[CheckResult]:
        built = ctx.executables(rule.unit) + ctx.libraries(rule.unit)
        if built:
            yield self.result(rule, "pass", f"Built {', '.join(p.name for p in built)}.", log=build.log)
        else:
            yield self.result(rule, "warn", "The build succeeded but produced no executable.", log=build.log)
