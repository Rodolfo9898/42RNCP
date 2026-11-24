"""What the subject lets a project use, as a section of a prompt."""

from __future__ import annotations

import re

from verdict.core.models import Rule
from verdict.reviews.prompts.text import short

# Rules that limit what a project may use: the functions of the subject's list, forbidden calls and keywords, and any sentence about
# libraries, packages or dependencies.
LIMIT_WORDS = re.compile(r"librar|dependenc|package|framework|external|authori[sz]ed|allowed function|forbidden|not allowed|only .{0,40}allowed",
                         re.I)
MAX_LIMITS = 12
EXTRA_FUNCTIONS = (("libft", "the project's own libft"), ("math", "every function of the math library"),
                   ("mlx", "MiniLibX"), ("own_allowed", "equivalents you write yourself"))


def _page(rule: Rule) -> str:
    return f" ({rule.sources[0].pdf} p.{rule.sources[0].page})" if rule.sources else ""


def _allowed_functions(rule: Rule) -> str:
    names = ", ".join(rule.params.get("functions") or []) or "none listed"
    extra = [text for flag, text in EXTRA_FUNCTIONS if rule.params.get(flag)]
    return (f"External functions allowed{_page(rule)}: {names}" + (f"; also {', '.join(extra)}" if extra else "")
            + ". Any other external function, and any library not named here, is forbidden.")


def library_limits(rules: list[Rule] | None) -> list[str]:
    """What the subject allows a project to use, one line each, from the rules extracted from it. Empty when it says nothing."""
    lines: dict[str, None] = {}
    for rule in rules or []:
        if rule.kind == "allowed_functions":
            lines.setdefault(_allowed_functions(rule))
        elif rule.kind in ("cpp_forbidden_calls", "cpp_forbidden_keywords"):
            names = ", ".join(rule.params.get("names") or [])
            lines.setdefault(f"Forbidden{_page(rule)}: {rule.title}" + (f" ({names})" if names else ""))
        elif rule.kind in ("manual", "language") and rule.text and LIMIT_WORDS.search(rule.text):
            lines.setdefault(f"{short(rule.text, 300)}{_page(rule)}")
    return list(lines)[:MAX_LIMITS]


def limits_section(rules: list[Rule] | None, lang: str | None) -> str:
    """The text of a prompt about what may be used, so that nothing forbidden is added while fixing or suggesting."""
    lines = library_limits(rules)
    listed = "\n".join(f"- {line}" for line in lines) if lines else (
        "- The subject lists no libraries or functions, so the rule is: add nothing that is not already used by the project, "
        "and ask before adding a dependency of any kind.")
    where = {"c": "`#include`, a call, a `-l` flag in the Makefile", "cpp": "`#include`, a call, a `-l` flag in the Makefile"}.get(
        lang or "", "an import, a call, a package or dependency in a manifest, a Dockerfile or the Makefile")
    return (f"WHAT THE SUBJECT LETS THE PROJECT USE (a hard limit: staying inside it is part of the task):\n{listed}\n"
            f"Before you write {where}, or anything else that brings in outside code, check it against this.\n"
            "If it is not allowed, do not add it: solve the problem with your own code or what the project already uses. A fix that needs something "
            "forbidden is not made: report it as not fixed and say why.\nThis also holds for a Dockerfile you change and for test "
            "helpers (they run in the project's environment, but they must not make the project itself depend on a forbidden library).")
