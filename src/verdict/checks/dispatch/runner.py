"""Running every check of a review."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from verdict.checks.context.ctx import Ctx
from verdict.checks.dispatch.registry import CheckerRegistry, default_registry
from verdict.checks.engine.checker import Audit
from verdict.checks.engine.results import label, result
from verdict.core.models import CheckResult, Rule
from verdict.gateways.sandbox import SandboxError


class CheckRun:
    """One review of one repository: the opening audits, then each rule by phase (a rule of an unsubmitted bonus is noted once and
    left out), then the closing audits. A bug in one check never aborts the review."""

    def __init__(self, ctx: Ctx, emit: Callable[[CheckResult], None], registry: CheckerRegistry) -> None:
        self.ctx, self.emit, self.registry = ctx, emit, registry

    def run(self) -> None:
        self._audit(self.registry.opening)
        self._rules()
        self._audit(self.registry.closing)

    def _audit(self, audits: Iterable[Audit]) -> None:
        for audit in audits:
            if audit.needs_sandbox and self.ctx.sandbox is None:
                continue
            for res in audit.run(self.ctx):
                self.emit(res)

    def _rules(self) -> None:
        bonus_submitted = self.ctx.has_bonus()
        bonus_noted = False
        for rule in sorted(self.ctx.rules, key=lambda r: self.registry.phase_of(r.kind)):
            if rule.section == "bonus" and not bonus_submitted:
                if not bonus_noted:
                    bonus_noted = True
                    self.emit(self._bonus_note())
                continue
            self._check(rule)

    def _check(self, rule: Rule) -> None:
        try:
            for res in self.registry.for_kind(rule.kind).run(self.ctx, rule):
                self.emit(res)
        except SandboxError as exc:
            self.emit(result(rule, "skipped", f"Needs the sandbox: {exc}", title=label(rule)))
        except Exception as exc:  # a bug in one check must not abort the review
            self.emit(result(rule, "warn", f"The check itself crashed: {type(exc).__name__}: {exc}", title=label(rule)))

    @staticmethod
    def _bonus_note() -> CheckResult:
        return CheckResult(
            rule_id=None, title="Bonus part not submitted", status="skipped", section="bonus",
            detail="No bonus files or `bonus` rule found, so the bonus requirements were not evaluated.",
        )


def run_checks(ctx: Ctx, emit: Callable[[CheckResult], None], registry: CheckerRegistry | None = None) -> None:
    """Every rule of the review against the repository, and the audits around them; each result goes to `emit` as it is known."""
    CheckRun(ctx, emit, registry or default_registry()).run()
