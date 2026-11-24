from __future__ import annotations

import re

from verdict.subjects.spec.model import Line


def prose_items(lines: list[Line]) -> list[tuple[str, Line]]:
    """Group wrapped lines into bullet items / paragraphs, and those into sentences (each with the line it starts on)."""
    items: list[tuple[str, Line]] = []
    buf = ""
    head: Line | None = None
    for line in lines:
        starts = line.text[:1] in "•◦" or (buf and re.search(r"[.!?:]$", buf))
        if buf and starts:
            items.append((buf, head))  # type: ignore[arg-type]
            buf, head = "", None
        if not buf:
            head = line
        buf = (buf + " " + line.text).strip()
    if buf and head:
        items.append((buf, head))
    out: list[tuple[str, Line]] = []
    for text, line in items:
        text = re.sub(r"(\w)- (\w)", r"\1\2", text)  # un-hyphenate wrapped words
        text = re.sub(r"^[•◦]\s*", "", text)
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z•])", text):
            if 25 <= len(sentence) <= 500:
                out.append((sentence.strip(), line))
    return out


def line_of(lines: list[Line], head: Line, needle: str) -> Line:
    """The line a sentence really sits on: wrapped paragraphs are credited to their first line, which can be pages earlier."""
    start = next((i for i, l in enumerate(lines) if l is head), 0)
    return next((l for l in lines[start:start + 80] if needle.lower() in l.text.lower()), head)
