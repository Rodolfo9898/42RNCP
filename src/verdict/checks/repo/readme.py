"""The README the common-core subjects dictate."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker
from verdict.core.models import CheckResult, Evidence, Rule

FIRST_LINE = re.compile(r"([*_])\s*This project has been created as part of the 42 curriculum by .+?\s*\1", re.I)
AI_MENTION = re.compile(r"\bAI\b|artificial intelligence|chatgpt|claude|copilot|gemini|\bLLM\b", re.I)


class ReadmeChecker(Checker):
    """README.md at the root: the italic first line, the required sections, and a word on how AI was used."""

    kind = "readme"

    def prepare(self, ctx: Ctx, rule: Rule) -> list[Path]:
        return [p for p in ctx.files() if len(p.parts) == 1]

    def evaluate(self, ctx: Ctx, rule: Rule, root_files: list[Path]) -> Iterable[CheckResult]:
        exact = next((p for p in root_files if p.name == "README.md"), None)
        if exact is None:
            yield self._missing(rule, root_files)
            return
        lines = ctx.read(exact).splitlines()
        first = next((l.strip() for l in lines if l.strip()), "")
        headings = [(i, re.sub(r"[:#*_`\s]+", " ", l).strip().lower()) for i, l in enumerate(lines)
                    if re.match(r"\s{0,3}#{1,6}\s+\S", l)]
        problems = self._problems(rule, first, headings)
        evidence = [Evidence(file="README.md", line=1, snippet=first[:160])]
        if problems:
            yield self.result(rule, "fail", "README.md: " + "; ".join(problems) + ".", evidence=evidence)
            return
        silent_on_ai = self._resources_without_ai(lines, headings)
        if silent_on_ai is not None:
            yield self.result(rule, "warn", "README.md is complete, but its Resources section does not say how AI was used (the subject asks for it, even if the answer is “not used”).",
                              evidence=[Evidence(file="README.md", line=silent_on_ai + 1)])
            return
        yield self.result(rule, "pass", f"README.md has the required first line and sections ({len(lines)} lines).")

    def _missing(self, rule: Rule, root_files: list[Path]) -> CheckResult:
        other = next((p for p in root_files if p.name.lower().startswith("readme")), None)
        if other:
            return self.result(rule, "fail", f"Found `{other.name}`, but the subject requires a file named exactly README.md at the root.")
        return self.result(rule, "fail", "No README.md found at the root of the repository. The subject requires one.")

    @staticmethod
    def _problems(rule: Rule, first: str, headings: list[tuple[int, str]]) -> list[str]:
        problems: list[str] = []
        if not FIRST_LINE.fullmatch(first):
            problems.append("the very first line must be italicized and read: *This project has been created as part of the 42 curriculum by <login>*")
        elif re.search(r"<\s*login", first, re.I):
            problems.append("the first line still contains the <login> placeholder")
        for section in rule.params["sections"]:
            if not any(section.lower() in h for _, h in headings):
                problems.append(f"missing a “{section}” section")
        return problems

    @staticmethod
    def _resources_without_ai(lines: list[str], headings: list[tuple[int, str]]) -> int | None:
        """The line of the Resources heading when that section never says how AI was used; None when it does (or there is none)."""
        resources = next((i for i, h in headings if "resources" in h), None)
        if resources is None:
            return None
        end = next((i for i, _ in headings if i > resources), len(lines))
        return None if AI_MENTION.search("\n".join(lines[resources:end])) else resources
