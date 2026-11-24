"""The rules nothing can check by script."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker
from verdict.core.models import CheckResult, Rule


class ManualChecker(Checker):
    """The rule is listed for a human (and stands in, as a Null Object, for a kind no checker handles): nothing is checked, so nothing
    is claimed."""

    kind = "manual"

    def evaluate(self, ctx: Ctx, rule: Rule, facts: Any) -> Iterable[CheckResult]:
        yield self.result(rule, "manual", rule.text, auto=False)
