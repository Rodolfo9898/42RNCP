"""Finding the function definitions of C-like code."""

from __future__ import annotations

import re
from collections.abc import Iterable


def functions(code: str) -> Iterable[tuple[str, int, int]]:
    """(name, first line, last line) of function definitions in comment-free C-like code."""
    lines = code.split("\n")
    depth = 0
    start = None
    name = ""
    previous_signature = ""
    for number, line in enumerate(lines, 1):
        opens, closes = line.count("{"), line.count("}")
        if depth == 0 and opens:
            signature = line if ")" in line.split("{")[0] else previous_signature
            if re.search(r"\)\s*(const\s*)?$", signature.split("{")[0].rstrip()) and not re.match(r"\s*(struct|enum|union|typedef|namespace|class)\b", signature):
                m = list(re.finditer(r"([~\w:]+)\s*\(", signature))
                name = m[0].group(1) if m else "?"
                start = number
        depth += opens - closes
        if depth == 0 and start is not None and closes:
            yield name, start, number
            start = None
        if line.strip():
            previous_signature = line if depth == 0 else previous_signature
