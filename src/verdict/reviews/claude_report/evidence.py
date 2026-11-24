"""The files and lines claude cites."""

from __future__ import annotations

import re

from verdict.core.models import Evidence


def citations(raw: object, files: dict[str, int]) -> list[Evidence]:
    """'file:line', 'file:12-20' or 'file:7,9' -> Evidence, keeping only files and lines that exist."""
    out: list[Evidence] = []
    for entry in raw if isinstance(raw, list) else []:
        match = re.match(r"^\s*(?:\./)?(.+?)(?::(\d+))?(?:[-,–]\d+)*\s*$", str(entry))
        if not match:
            continue
        file, line = match.group(1), int(match.group(2)) if match.group(2) else None
        total = files.get(file)
        if total is None or (line is not None and not 1 <= line <= total):
            continue
        out.append(Evidence(file=file, line=line))
        if len(out) >= 5:
            break
    return out
