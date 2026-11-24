"""The wording a subject's prose uses to state a requirement, and the words that are not function names."""

from __future__ import annotations

import re

REQUIREMENT_WORDS = re.compile(
    r"\b(must|should|forbidden|not allowed|prohibited|mandatory|required|cannot|can't|"
    r"should not|shouldn't|grade will be|will (?:receive|be considered)|strictly)\b",
    re.I,
)

# Sentences about how the subject is read or graded, not about the project: nothing in the repository can satisfy them, so they are
# not worth a "needs manual review" line (the bonus being judged only if the mandatory part is perfect, sections of the README "that may
# be required", additions "listed below").
ABOUT_THE_SUBJECT = re.compile(
    r"\bbonus\b.{0,80}\b(?:will only be|won[’']?t be|will not be|is only|are only|only counts?|only be)\b.{0,40}"
    r"\b(?:evaluated|considered|graded|assessed|taken into account|counted)\b"
    r"|\b(?:additional|extra|optional) sections? (?:may|might|can) be required\b"
    r"|\bany required additions? (?:will|would) be\b",
    re.I,
)

DEFAULT_MAKEFILE_RULES = ["NAME", "all", "clean", "fclean", "re"]

# Words that show up in 'External Function' prose but are not function names.
NOT_FUNCTIONS = {
    "or", "any", "equivalent", "coded", "all", "functions", "function", "of", "the", "library",
    "math", "minilibx", "lm", "compiler", "option", "man", "and", "in", "c", "implemented",
    "functionality", "must", "be", "detailed", "below", "none", "n", "a", "your", "own",
}


def identifiers(text: str) -> list[str]:
    """The names in 'External Function' prose, once each and in order of appearance."""
    seen: dict[str, None] = {}
    for name in re.findall(r"\b[a-z_][a-z0-9_]*\b", text):
        if name not in NOT_FUNCTIONS:
            seen.setdefault(name)
    return list(seen)
