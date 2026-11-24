"""The files the subject asks to turn in."""

from __future__ import annotations

from collections.abc import Iterable

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker
from verdict.checks.engine.results import label
from verdict.checks.files.finder import RuleSearch, Search, after_make
from verdict.checks.files.messages import elsewhere_text, expected_text, moved_text, note_text
from verdict.core.models import CheckResult, Rule

AFTER_MAKE_NOTE = " Some of them only appear once `make` has run (a submodule or a download in the Makefile), which counts."


class RequiredFilesChecker(Checker):
    """Every file or folder the subject lists is there (a pattern may be met anywhere in the project when the layout is free; the
    strict projects keep the subject's format). A name found elsewhere is a question about structure, not a missing file."""

    kind = "required_files"

    def title(self, rule: Rule) -> str:
        return label(rule)

    def skip(self, ctx: Ctx, rule: Rule) -> CheckResult | None:
        if not ctx.unit_dir(rule.unit).is_dir():
            return self.result(rule, "fail", f"Directory `{rule.unit}/` does not exist in the repository.")
        return None

    def prepare(self, ctx: Ctx, rule: Rule) -> Search:
        return RuleSearch(ctx, rule).run()

    def evaluate(self, ctx: Ctx, rule: Rule, search: Search) -> Iterable[CheckResult]:
        made = ""
        if search.missing:
            # "Copy it into your repository" is met by any way of getting it there, as long as the files are there once `make` ran.
            build = after_make(ctx, rule.unit)
            if build is not None:
                before = len(search.missing)
                search = RuleSearch(ctx, rule).run()
                if len(search.missing) < before:
                    made = AFTER_MAKE_NOTE
                if search.missing and (reason := ctx.offline_reason(build)):
                    yield self.result(rule, "warn", f"Not in the repository: {', '.join(search.missing)}. They may come with the build, but {reason}",
                                      log=build.log)
                    return
        yield self._verdict(ctx, rule, search, made)

    def _verdict(self, ctx: Ctx, rule: Rule, search: Search, made: str) -> CheckResult:
        strict = ctx.strict_layout
        moved = moved_text(rule, ctx.moved_unit(rule.unit) if not strict else rule.unit)
        elsewhere, expected, notes = elsewhere_text(search, strict), expected_text(search, strict), note_text(rule)
        if search.missing:
            return self.result(rule, "fail", f"Missing: {', '.join(search.missing)}.{elsewhere}{expected}{moved}{notes}")
        if strict and (search.relocated or search.expected):
            return self.result(rule, "warn", f"Not exactly as the subject lists.{elsewhere}{expected}{notes}")
        return self.result(rule, "pass", f"All {search.found + len(search.relocated)} required file pattern(s) are present."
                                         f"{elsewhere}{expected}{moved}{made}{notes}")
