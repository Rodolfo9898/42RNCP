"""A page of a subject PDF as an image (the editor cannot embed a PDF viewer, but it can show images)."""

from __future__ import annotations

from verdict.core.errors import NotFound
from verdict.library.files import SubjectFiles
from verdict.sessions.store import Session
from verdict.subjects.pdf import render_page


class PageImages:
    LIMIT = 120                                       # pages kept rendered

    def __init__(self, files: SubjectFiles) -> None:
        self.files = files
        self._cache: dict[tuple, bytes] = {}

    def png(self, session: Session, name: str, page: int) -> bytes:
        path = self.files.pdf(session, name)
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size, page)
        if key not in self._cache:
            try:
                png = render_page(path, page)
            except IndexError:
                raise NotFound(f"{name} has no page {page}") from None
            if len(self._cache) > self.LIMIT:
                self._cache.clear()
            self._cache[key] = png
        return self._cache[key]
