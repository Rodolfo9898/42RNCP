from __future__ import annotations

from pathlib import Path

import pymupdf


def read_pages(source: Path | bytes) -> list[str]:
    """Return the text of each page of a PDF."""
    doc = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes) else pymupdf.open(source)
    with doc:
        return [page.get_text() for page in doc]


def render_page(source: Path, page: int, zoom: float = 2.0) -> bytes:
    """One page (1-based) as a PNG. IndexError when the page does not exist."""
    with pymupdf.open(source) as doc:
        if not 1 <= page <= doc.page_count:
            raise IndexError(page)
        return doc[page - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
