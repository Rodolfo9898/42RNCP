"""Reading the code of a source file without being fooled by its comments and strings."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from verdict.checks.context.ctx import Ctx
from verdict.core.models import Evidence


def strip_code(text: str) -> str:
    """Blank out comments and string/char literals (keeping line numbers intact)."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        two = text[i:i + 2]
        if two == "//":
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            end = min(j, n)
            closed = end < n and text[end] == c
            out.append(c + re.sub(r"[^\n]", " ", text[i + 1:end]) + (c if closed else ""))
            i = end + (1 if closed else 0)
        else:
            out.append(c)
            i += 1
    return "".join(out)


def grep(ctx: Ctx, files: Iterable[Path], pattern: re.Pattern[str], *, code_only: bool = True,
         limit: int = 25) -> list[Evidence]:
    found: list[Evidence] = []
    for rel in files:
        raw = ctx.read(rel)
        text = strip_code(raw) if code_only else raw
        raw_lines = raw.splitlines()
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                snippet = raw_lines[number - 1].strip()[:200] if number <= len(raw_lines) else ""
                found.append(Evidence(file=rel.as_posix(), line=number, snippet=snippet))
                if len(found) >= limit:
                    return found
    return found
