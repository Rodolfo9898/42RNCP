"""What the Makefile says, read as text (nothing is run)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker
from verdict.checks.engine.results import label
from verdict.core.models import CheckResult, Evidence, Rule


def has_target(makefile: str, target: str) -> bool:
    if target == "NAME":
        return bool(re.search(r"^\s*NAME\s*[:+?]?=", makefile, re.M) or re.search(r"^\$\(NAME\)\s*:", makefile, re.M))
    return bool(re.search(rf"^(?:[\w.$()/-]+[ \t]+)*{re.escape(target)}(?:[ \t]+[\w.$()/-]+)*[ \t]*:(?!=)", makefile, re.M))


class MakefileRulesChecker(Checker):
    """The Makefile defines the rules the subject lists (NAME, all, clean, fclean, re)."""

    kind = "makefile_rules"

    def title(self, rule: Rule) -> str:
        return label(rule)

    def skip(self, ctx: Ctx, rule: Rule) -> CheckResult | None:
        if not (ctx.unit_dir(rule.unit) / "Makefile").is_file():
            return self.result(rule, "fail", f"No Makefile in `{rule.unit}/`.")
        return None

    def evaluate(self, ctx: Ctx, rule: Rule, facts: Any) -> Iterable[CheckResult]:
        makefile = (ctx.unit_dir(rule.unit) / "Makefile").read_text(errors="replace")
        targets = list(dict.fromkeys(rule.params["targets"]))
        missing = [t for t in targets if not has_target(makefile, t)]
        if missing:
            yield self.result(rule, "fail", f"Makefile is missing: {', '.join(missing)}.")
        else:
            yield self.result(rule, "pass", f"Makefile defines {', '.join(targets)}.")


class BonusRuleChecker(Checker):
    """When bonus files were turned in, the Makefile has a `bonus` rule."""

    kind = "bonus_rule"

    def prepare(self, ctx: Ctx, rule: Rule) -> list[Path]:
        return [p for p in ctx.files() if re.search(r"bonus", p.name, re.I) and p.suffix in (".c", ".h", ".cpp", ".hpp")]

    def evaluate(self, ctx: Ctx, rule: Rule, bonus_files: list[Path]) -> Iterable[CheckResult]:
        if not bonus_files:
            yield self.result(rule, "na", "No bonus files in the repository, so no bonus rule is required.")
            return
        path = ctx.unit_dir(rule.unit) / "Makefile"
        text = path.read_text(errors="replace") if path.is_file() else ""
        if has_target(text, "bonus"):
            yield self.result(rule, "pass", "Bonus files found and the Makefile has a `bonus` rule.")
        else:
            yield self.result(rule, "fail", "Bonus files found but the Makefile has no `bonus` rule.",
                              evidence=[Evidence(file=p.as_posix()) for p in bonus_files[:10]])
