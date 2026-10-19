from __future__ import annotations

from pathlib import Path

import pymupdf


def read_pages(source: Path | bytes) -> list[str]:
    """Return the text of each page of a PDF."""
    doc = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes) else pymupdf.open(source)
    with doc:
        return [page.get_text() for page in doc]
