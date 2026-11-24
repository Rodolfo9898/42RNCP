"""Checks of what the sources are written in and how their headers are guarded."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker
from verdict.core.models import CheckResult, Evidence, Rule

OTHER_LANGUAGES = (".py", ".rs", ".go", ".java", ".js", ".ts", ".rb", ".php", ".cs")


class LanguageChecker(Checker):
    """The project is written in C (not C++), whatever else it carries along."""

    kind = "language"

    def evaluate(self, ctx: Ctx, rule: Rule, facts: Any) -> Iterable[CheckResult]:
        wrong_cpp = [p for p in ctx.files() if p.suffix.lower() in (".cpp", ".cc", ".hpp", ".cxx") and not ctx.is_vendored(p)]
        other = [p for p in ctx.files() if p.suffix.lower() in OTHER_LANGUAGES and not ctx.is_vendored(p)]
        if wrong_cpp:
            yield self.result(rule, "fail", "C++ files found in a C project.",
                              evidence=[Evidence(file=p.as_posix()) for p in wrong_cpp[:20]])
        elif not any(p.suffix == ".c" for p in ctx.files()):
            yield self.result(rule, "fail", "No .c files found.")
        elif other:
            yield self.result(rule, "pass", f"The project is written in C. The {len(other)} file(s) in other languages (test scripts, tools) are "
                                            "not part of the C code and do not count against it.",
                              evidence=[Evidence(file=p.as_posix()) for p in other[:20]])
        else:
            yield self.result(rule, "pass", "Only C sources found.")


class IncludeGuardsChecker(Checker):
    """Every header is guarded against being included twice."""

    kind = "include_guards"

    def evaluate(self, ctx: Ctx, rule: Rule, facts: Any) -> Iterable[CheckResult]:
        headers = [p for p in ctx.source_files() if p.suffix.lower() in (".h", ".hpp")]
        bad = []
        for rel in headers:
            text = ctx.read(rel)
            guarded = re.search(r"#\s*pragma\s+once", text) or re.search(r"#\s*ifndef\s+(\w+)\s*\n\s*#\s*define\s+\1\b", text)
            if not guarded:
                bad.append(Evidence(file=rel.as_posix(), snippet="no include guard"))
        if not headers:
            yield self.result(rule, "skipped", "No header files found.")
        elif bad:
            yield self.result(rule, "fail", f"{len(bad)} of {len(headers)} header(s) have no include guard.", evidence=bad)
        else:
            yield self.result(rule, "pass", f"All {len(headers)} header(s) have include guards.")
