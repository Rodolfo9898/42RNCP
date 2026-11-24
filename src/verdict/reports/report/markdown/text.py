"""Text helpers: results carry repo-controlled strings, so everything that goes into the document passes through here."""

from __future__ import annotations

import re

from verdict.core.models import Evidence


def code(text: str) -> str:
    text = " ".join(str(text).split())
    return f"`` {text} ``" if "`" in text else f"`{text}`"


def inline(text: str) -> str:
    """Single-line, markdown-neutral text. Balanced `code spans` are kept; everything else is escaped."""
    text = " ".join(text.split())
    parts = re.split(r"(`[^`]+`)", text)
    return "".join(
        part if len(part) > 2 and part.startswith("`") and part.endswith("`")
        else re.sub(r"([\\*_\[\]<>|`])", r"\\\1", part)
        for part in parts
    )


def where(e: Evidence) -> str:
    return f"{e.file}:{e.line}" if e.line else e.file


def sources(sources) -> str:
    return " _(" + ", ".join(f"{inline(s.pdf)} p.{s.page}" for s in sources[:3]) + ")_" if sources else ""


def fenced(text: str) -> list[str]:
    longest = max((len(run) for run in text.replace("\n", " ").split(" ") if set(run) == {"`"}), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence, text.rstrip(), fence]


def evidence_line(e: Evidence, indent: str = "  - ") -> str:
    """`file:line`, and the line of code when it was kept."""
    return f"{indent}{code(where(e))}" + (f" — {code(e.snippet)}" if e.snippet else "")
