from __future__ import annotations

import re


def is_toc_page(lines: list[str], previous_was_toc: bool) -> bool:
    """A page of the table of contents: it says so, or it follows one and is mostly page numbers."""
    if not lines:
        return False
    if lines[0].lower() in ("contents", "table of contents"):
        return True
    if not previous_was_toc:
        return False
    numeric = sum(1 for l in lines if re.fullmatch(r"\d+|[ivxlc]+", l, re.I))
    return numeric / len(lines) > 0.3
