"""The functions the subject asks for are defined, and in the library the Makefile builds."""

from __future__ import annotations

import re
from collections.abc import Iterable

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker, Phase
from verdict.checks.engine.results import label
from verdict.checks.functions.symbols import library_functions
from verdict.core.models import CheckResult, Rule

DEFINITION = r"^(?!static\b)[A-Za-z_][\w \t\*]*[ \t\*]{name}\s*\("


class FunctionsDefinedChecker(Checker):
    """Every function the subject lists is defined in the sources, and (with a sandbox) present in the library `make` builds."""

    kind = "functions_defined"
    phase = Phase.ANALYSIS

    def prepare(self, ctx: Ctx, rule: Rule) -> list[str]:
        """The names missing from the sources."""
        sources = [p for p in ctx.source_files(rule.unit) if p.suffix == ".c"]
        text = "\n".join(ctx.read(p) for p in sources)
        return [n for n in rule.params["names"] if not re.search(DEFINITION.format(name=re.escape(n)), text, re.M)]

    def evaluate(self, ctx: Ctx, rule: Rule, missing: list[str]) -> Iterable[CheckResult]:
        names = rule.params["names"]
        if missing:
            yield self.result(rule, "fail", f"{len(missing)} of {len(names)} required function(s) not found in the sources: {', '.join(missing)}.")
            return
        # Defined in the sources is not enough: they must be in the library that `make` actually builds.
        library = self._built_library(ctx, rule)
        if library is None:
            yield self.result(rule, "pass", f"All {len(names)} required function(s) are defined in the sources.")
            return
        built = library_functions(ctx, rule.unit, library)
        absent = [n for n in names if n not in built]
        title = label(rule, f"Required functions are in {library}")
        if absent:
            yield self.result(rule, "fail",
                              f"{len(absent)} of {len(names)} required function(s) are in the sources but NOT in the {library} that `make` builds: "
                              f"{', '.join(absent)}. Check which Makefile rule adds them: the subject requires them in the library.", title=title)
        else:
            yield self.result(rule, "pass", f"All {len(names)} required function(s) are defined in the sources and present in {library}.", title=title)

    @staticmethod
    def _built_library(ctx: Ctx, rule: Rule) -> str | None:
        library = next((n for n in ctx.programs(rule.unit, rule.section) if n.endswith(".a")), None)
        if library and ctx.sandbox is not None and ctx.build(rule.unit).ok and (ctx.unit_dir(rule.unit) / library).is_file():
            return library
        return None
