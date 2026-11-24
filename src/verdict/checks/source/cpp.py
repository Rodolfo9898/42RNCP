"""The C++ modules' rules about what the sources may call, name or include."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker
from verdict.checks.source.text import grep
from verdict.core.models import CheckResult, Rule

FORBIDDEN_CALLS = re.compile(r"(?<![\w.>])(?:[vfsdn]*printf|malloc|calloc|realloc|free)\s*\(")
FORBIDDEN_KEYWORDS = re.compile(r"\busing\s+namespace\b|\bfriend\b")
STL_HEADERS = re.compile(
    r"#\s*include\s*<(vector|list|map|multimap|set|multiset|stack|queue|deque|algorithm|iterator|"
    r"unordered_map|unordered_set|array|bitset|functional|numeric)>"
)


class CppForbiddenCallsChecker(Checker):
    """No *printf(), *alloc() or free() call in the code."""

    kind = "cpp_forbidden_calls"

    def evaluate(self, ctx: Ctx, rule: Rule, facts: Any) -> Iterable[CheckResult]:
        hits = grep(ctx, ctx.source_files(), FORBIDDEN_CALLS)
        if hits:
            yield self.result(rule, "fail", "Forbidden call(s) found (grade 0 per the subject).", evidence=hits)
        else:
            yield self.result(rule, "pass", "No *printf(), *alloc() or free() calls found.")


class CppForbiddenKeywordsChecker(Checker):
    """Neither `using namespace` nor `friend`."""

    kind = "cpp_forbidden_keywords"

    def evaluate(self, ctx: Ctx, rule: Rule, facts: Any) -> Iterable[CheckResult]:
        hits = grep(ctx, ctx.source_files(), FORBIDDEN_KEYWORDS)
        if hits:
            yield self.result(rule, "fail", "`using namespace` / `friend` used (forbidden unless the exercise says otherwise).", evidence=hits)
        else:
            yield self.result(rule, "pass", "Neither `using namespace` nor `friend` appears.")


class CppNoStlChecker(Checker):
    """No STL container or algorithm header before module 08."""

    kind = "cpp_no_stl"

    def skip(self, ctx: Ctx, rule: Rule) -> CheckResult | None:
        module = rule.params.get("module")
        if module is None or module >= 8:
            return self.result(rule, "skipped", "The STL is allowed in this module.")
        return None

    def evaluate(self, ctx: Ctx, rule: Rule, facts: Any) -> Iterable[CheckResult]:
        hits = grep(ctx, ctx.source_files(), STL_HEADERS, code_only=False)
        if hits:
            yield self.result(rule, "fail", "STL containers/algorithms are forbidden before module 08 (grade -42).", evidence=hits)
        else:
            yield self.result(rule, "pass", "No STL container or algorithm headers included.")
