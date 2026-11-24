"""The Norm, and the global variables it forbids: both read norminette's report."""

from __future__ import annotations

from collections.abc import Iterable

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker, Phase
from verdict.checks.norm.report import NormReport, norm_report
from verdict.core.models import CheckResult, Evidence, Rule


class NormChecker(Checker):
    """No Norm error in the student's own code (MiniLibX, which they were given, is left out and said so)."""

    kind = "norm"
    phase = Phase.ANALYSIS

    def skip(self, ctx: Ctx, rule: Rule) -> CheckResult | None:
        return self.result(rule, "skipped", "The Norm does not apply to C++ projects.") if ctx.lang == "cpp" else None

    def prepare(self, ctx: Ctx, rule: Rule) -> NormReport:
        return norm_report(ctx)

    def evaluate(self, ctx: Ctx, rule: Rule, report: NormReport) -> Iterable[CheckResult]:
        left_out = self._left_out(ctx)
        if not report.available:
            yield self.result(rule, "skipped", "norminette is not installed in the sandbox.")
            return
        if report.files == 0:
            yield self.result(rule, "fail", "No .c/.h files to check.")
            return
        errors = {f: [e for e in errs if e.kind == "Error"] for f, errs in report.errors.items()}
        errors = {f: errs for f, errs in errors.items() if errs}
        if errors:
            evidence = [Evidence(file=f, line=e.line, snippet=f"{e.code}: {e.message}") for f, errs in errors.items() for e in errs][:60]
            total = sum(len(v) for v in errors.values())
            yield self.result(rule, "fail", f"{total} Norm error(s) in {len(errors)} of {report.files} file(s).{left_out}", evidence=evidence)
        else:
            yield self.result(rule, "pass", f"norminette: all {report.files} file(s) OK.{left_out}")

    @staticmethod
    def _left_out(ctx: Ctx) -> str:
        vendored = sorted(set(ctx.minilibx_dirs()) | {p.parent.as_posix() for p in ctx.files() if p.name == "mlx.h" and ctx.is_vendored(p)})
        if not vendored:
            return ""
        return (f" MiniLibX ({', '.join(f'`{d}/`' for d in vendored[:3])}) is not checked: it is given to the students, not "
                "written by them.")


class NoGlobalsChecker(Checker):
    """norminette detected no global variable (the subject may allow some: the manual items say)."""

    kind = "no_globals"
    phase = Phase.ANALYSIS

    def skip(self, ctx: Ctx, rule: Rule) -> CheckResult | None:
        return self.result(rule, "skipped", "Not checked for C++ projects.") if ctx.lang == "cpp" else None

    def prepare(self, ctx: Ctx, rule: Rule) -> NormReport:
        return norm_report(ctx)

    def evaluate(self, ctx: Ctx, rule: Rule, report: NormReport) -> Iterable[CheckResult]:
        if not report.available:
            yield self.result(rule, "manual", rule.text, auto=False)
            return
        hits = [Evidence(file=f, line=e.line, snippet=e.message) for f, errs in report.errors.items()
                for e in errs if e.code == "GLOBAL_VAR_DETECTED"]
        if hits:
            yield self.result(rule, "fail", f"{len(hits)} global variable(s) detected by norminette.", evidence=hits[:30])
        else:
            yield self.result(rule, "pass", "norminette detected no global variables (the subject may allow some; see the manual items).")
