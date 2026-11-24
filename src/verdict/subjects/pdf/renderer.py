from __future__ import annotations

from pathlib import Path

import pymupdf


def render_page(source: Path, page: int, zoom: float = 2.0) -> bytes:
    """One page (1-based) as a PNG. IndexError when the page does not exist."""
    with pymupdf.open(source) as doc:
        if not 1 <= page <= doc.page_count:
            raise IndexError(page)
        return doc[page - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
