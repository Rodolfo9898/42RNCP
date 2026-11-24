"""Smoke tests: the built programs are run a few times with generic arguments."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker, Phase
from verdict.checks.engine.results import tail
from verdict.checks.runtime.targets import runnable_targets
from verdict.core.models import CheckResult, Rule

SMOKE_ARGS = ((), ("abc",), ("1", "2", "3"), ("-1",))
LEAK_ARGS = ((), ("abc",), ("3", "2", "1"))


class NoCrashChecker(Checker):
    """No program is killed by a signal when run with no arguments, invalid ones or a few numbers."""

    kind = "no_crash"
    phase = Phase.RUNTIME

    def prepare(self, ctx: Ctx, rule: Rule) -> list[tuple[str, Path]]:
        return runnable_targets(ctx)

    def evaluate(self, ctx: Ctx, rule: Rule, targets: list[tuple[str, Path]]) -> Iterable[CheckResult]:
        if not targets:
            yield self.result(rule, "skipped", "No executable was built (libraries need a test program; see the manual items).")
            return
        crashes: list[str] = []
        runs = 0
        for unit, exe in targets:
            for args in SMOKE_ARGS:
                runs += 1
                res = ctx.run([f"./{exe.name}", *args], unit, timeout=5)
                if res.crashed:
                    crashes.append(f"$ ./{exe.name} {' '.join(args)}\n  killed by signal {-res.rc}\n{tail(res.output, 5)}")
        if crashes:
            yield self.result(rule, "fail", f"{len(crashes)} of {runs} basic run(s) crashed.", log="\n\n".join(crashes))
        else:
            yield self.result(rule, "pass", f"{runs} basic run(s) (no arguments, invalid arguments, a few numbers) did not crash. "
                                            "This is a smoke test, not a full evaluation.")


class NoLeaksChecker(Checker):
    """valgrind finds no definite leak in a few basic runs of each program."""

    kind = "no_leaks"
    phase = Phase.RUNTIME

    def prepare(self, ctx: Ctx, rule: Rule) -> list[tuple[str, Path]]:
        return runnable_targets(ctx)

    def evaluate(self, ctx: Ctx, rule: Rule, targets: list[tuple[str, Path]]) -> Iterable[CheckResult]:
        if not targets:
            yield self.result(rule, "skipped", "No executable was built (libraries need a test program).")
            return
        leaks: list[str] = []
        runs = 0
        for unit, exe in targets:
            for args in LEAK_ARGS:
                res = ctx.run(["valgrind", "--leak-check=full", "--errors-for-leak-kinds=definite",
                               "--error-exitcode=42", "-q", f"./{exe.name}", *args], unit, timeout=60)
                if res.rc == 127:
                    yield self.result(rule, "skipped", "valgrind is not installed in the sandbox.")
                    return
                if res.timed_out:
                    continue
                runs += 1
                if res.rc == 42:
                    leaks.append(f"$ valgrind ./{exe.name} {' '.join(args)}\n{tail(res.stderr, 20)}")
        yield self._verdict(rule, leaks, runs)

    def _verdict(self, rule: Rule, leaks: list[str], runs: int) -> CheckResult:
        if leaks:
            return self.result(rule, "fail", f"valgrind reports leaks/errors in {len(leaks)} of {runs} run(s).", log="\n\n".join(leaks))
        if runs == 0:
            return self.result(rule, "skipped", "Every run timed out under valgrind.")
        return self.result(rule, "pass", f"valgrind found no definite leaks in {runs} basic run(s). Leaks on other inputs are not covered.")
