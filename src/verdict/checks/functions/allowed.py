"""Only the external functions the subject authorizes."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker, Phase
from verdict.checks.functions.symbols import imported_symbols
from verdict.checks.source.text import grep
from verdict.core.models import CheckResult, Evidence, Rule
from verdict.subjects.spec import MATH_FUNCTIONS

COMPILER_EMITTED = frozenset({"memcpy", "memset", "memmove", "memcmp"})


@dataclass
class Imports:
    inspected: bool = False                   # something was built (or compiled) to look at
    note: str = ""
    forbidden: set[str] = field(default_factory=set)


class AllowedFunctionsChecker(Checker):
    """The program imports nothing outside the list of the subject, and none of the project's own sources calls a forbidden function."""

    kind = "allowed_functions"
    phase = Phase.ANALYSIS

    def skip(self, ctx: Ctx, rule: Rule) -> CheckResult | None:
        return self.result(rule, "manual", rule.text, auto=False) if ctx.lang == "cpp" else None

    def prepare(self, ctx: Ctx, rule: Rule) -> Imports:
        unit = rule.unit
        targets = [n for n in ctx.programs(unit, rule.section) if (ctx.unit_dir(unit) / n).is_file()]
        note = ""
        if not targets:
            # No program name in the subject (e.g. get_next_line): compile each source to an object.
            targets, note = self._compiled_sources(ctx, unit), " (compiled from sources)"
        if not targets:
            return Imports()
        undefined, _defined = imported_symbols(ctx, unit, targets)
        undefined = {u for u in undefined if not u.startswith("_")}
        mlx = rule.params.get("mlx")
        forbidden = {u for u in undefined - self._allowed(rule) if not (mlx and re.match(r"(mlx_|X[A-Za-z]|shm)", u))}
        return Imports(True, note, forbidden)

    @staticmethod
    def _compiled_sources(ctx: Ctx, unit: str) -> list[str]:
        objs: list[str] = []
        for i, rel in enumerate(p for p in ctx.source_files(unit) if p.suffix == ".c"):
            out = f"/tmp/verdict_{abs(hash(str(ctx.repo)))}_{i}.o"
            source = str((ctx.repo / rel).resolve().relative_to(ctx.unit_dir(unit)))
            res = ctx.run(["cc", "-c", "-D", "BUFFER_SIZE=42", "-I.", "-o", out, source], unit, timeout=60)
            if res.ok:
                objs.append(out)
        return objs

    @staticmethod
    def _allowed(rule: Rule) -> set[str]:
        allowed = set(rule.params["functions"])
        if rule.params.get("libft"):
            allowed |= {"malloc", "free", "write"}
        if rule.params.get("math"):
            allowed |= set(MATH_FUNCTIONS) | {f + "f" for f in MATH_FUNCTIONS} | {f + "l" for f in MATH_FUNCTIONS}
        return allowed

    @staticmethod
    def _own_calls(ctx: Ctx, unit: str, forbidden: set[str]) -> tuple[list[str], list[Evidence]]:
        """The program also imports what its libraries use internally (MiniLibX calls getenv and strlen, for example). Only a call
        in the repo's own sources counts against it."""
        violations: list[Evidence] = []
        called: list[str] = []
        sources = ctx.source_files(unit)
        for name in sorted(forbidden):
            hits = grep(ctx, sources, re.compile(rf"(?<![\w.>])\b{re.escape(name)}\s*\("), limit=5)
            if hits:
                called.append(name)
                violations += hits
        return called, violations

    def evaluate(self, ctx: Ctx, rule: Rule, imports: Imports) -> Iterable[CheckResult]:
        if not imports.inspected:
            yield self.result(rule, "skipped", "Nothing was built, so external calls could not be inspected.")
            return
        note, forbidden = imports.note, imports.forbidden
        called, violations = self._own_calls(ctx, rule.unit, forbidden)
        if violations:
            yield self.result(rule, "fail", f"Calls to functions that are not authorized: {', '.join(called)}.{note}", evidence=violations[:25])
        elif forbidden and forbidden <= COMPILER_EMITTED:
            yield self.result(rule, "pass", f"Only compiler-generated calls to {', '.join(sorted(forbidden))}.{note}")
        else:
            extra = f" ({len(forbidden)} imported symbol(s) come from linked libraries, not from the repo's own calls.)" if forbidden else ""
            yield self.result(rule, "pass", f"No unauthorized function calls found{note}.{extra}")
