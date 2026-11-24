"""What a second `make` does."""

from __future__ import annotations

import re
from collections.abc import Iterable

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker, Phase
from verdict.core.models import CheckResult, Evidence, Rule

ARCHIVE_OR_LINK_LINE = re.compile(r"^\s*@?\s*(?:\S*/)?(?:cc|gcc|clang|c\+\+|g\+\+|clang\+\+|ar|ranlib|ld)\b")


class NoRelinkChecker(Checker):
    """Right after a build, `make -n` has nothing left to compile, archive or link (the Makefile does not relink for nothing)."""

    kind = "no_relink"
    phase = Phase.ANALYSIS

    def prepare(self, ctx: Ctx, rule: Rule) -> tuple[int, list[Evidence]]:
        offenders: list[Evidence] = []
        checked = 0
        for unit in ctx.units():
            if not ctx.has_makefile(unit) or not ctx.build(unit).ok:
                continue
            checked += 1
            res = ctx.run(["make", "-n"], unit, timeout=60)
            for line in res.stdout.splitlines():
                if ARCHIVE_OR_LINK_LINE.match(line):
                    offenders.append(Evidence(file=f"{unit}/Makefile".lstrip("./"), snippet=line.strip()[:200]))
        return checked, offenders

    def evaluate(self, ctx: Ctx, rule: Rule, facts: tuple[int, list[Evidence]]) -> Iterable[CheckResult]:
        checked, offenders = facts
        if checked == 0:
            yield self.result(rule, "skipped", "Nothing was built, so relinking could not be tested.")
        elif offenders:
            yield self.result(rule, "fail", "A second `make` would rebuild/relink although nothing changed.", evidence=offenders[:10])
        else:
            yield self.result(rule, "pass", "A second `make` has nothing to do.")
