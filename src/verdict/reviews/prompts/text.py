"""Small text helpers and wording shared by the prompts."""

from __future__ import annotations

LANGUAGES = {"c": "C", "cpp": "C++98"}        # by the language of the subject
DEFAULT_LANGUAGE = "the language the subject requires"


def short(text: str, limit: int = 160) -> str:
    """One line, at most `limit` characters."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
