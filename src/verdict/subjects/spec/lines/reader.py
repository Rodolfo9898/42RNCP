from __future__ import annotations

import re
from collections import Counter

from verdict.core.models import Section
from verdict.subjects.spec.lines.contents import is_toc_page
from verdict.subjects.spec.model import Line
from verdict.subjects.spec.vocabulary import label_of

PAGE_NUMBER = re.compile(r"\d+")
CHAPTER_MARK = re.compile(r"chapter [ivxlc]+", re.I)
PART_MARK = re.compile(r"(mandatory|bonus) part", re.I)
DELIVERABLES = re.compile(r"deliverable|submission|turn-?in")


class LineReader:
    """Flattens pages into lines, dropping TOC pages, page numbers and running headers, and stamps each line with the chapter and
    the part (mandatory or bonus) it belongs to. It follows the headings as it reads, so one reader reads one subject."""

    def __init__(self, pages: list[str]) -> None:
        self.pages = [[l.strip() for l in p.splitlines() if l.strip()] for p in pages]
        self.counts = Counter(l for page in self.pages for l in set(page))
        self.repeated = max(3, int(len(pages) * 0.4))
        self.section: Section = "mandatory"
        self.chapter = ""
        self.expect_title = False

    def read(self) -> list[Line]:
        out: list[Line] = []
        toc = False
        for number, page in enumerate(self.pages, 1):
            toc = is_toc_page(page, toc)
            if toc:
                continue
            for text in page:
                line = self._line(text, number)
                if line is not None:
                    out.append(line)
        return out

    def _is_noise(self, text: str) -> bool:
        """A page number, or a running header (a line that repeats on many pages, unless it labels a table)."""
        return bool(PAGE_NUMBER.fullmatch(text)) or (self.counts[text] >= self.repeated and label_of(text) is None)

    def _line(self, text: str, number: int) -> Line | None:
        if self._is_noise(text):
            return None
        if CHAPTER_MARK.fullmatch(text):
            self.expect_title = True
            return None
        heading = self.expect_title
        if heading:
            self._open_chapter(text)
        part = PART_MARK.fullmatch(text)
        if part:
            self.section = "bonus" if part.group(1).lower() == "bonus" else "mandatory"
            self.chapter = text.lower()
            return None
        return None if heading else Line(text, number, self.section, self.chapter)      # chapter titles are structure, not content

    def _open_chapter(self, title: str) -> None:
        self.chapter = title.lower()
        self.expect_title = False
        if DELIVERABLES.search(self.chapter):
            self.section = "mandatory"           # what to hand in concerns the whole project, not the bonus part that came before


def read_lines(pages: list[str]) -> list[Line]:
    return LineReader(pages).read()
