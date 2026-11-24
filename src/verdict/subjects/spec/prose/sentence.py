from __future__ import annotations

import re
from dataclasses import dataclass, field

from verdict.core.models import Source
from verdict.subjects.spec.model import Line


@dataclass
class Sentence:
    """One sentence of the subject's prose with where it was read: the line it sits on, the subject, and the C++ module (if any)."""

    text: str
    line: Line
    pdf: str
    module: int | None = None
    low: str = field(init=False)

    def __post_init__(self) -> None:
        self.low = self.text.lower()

    @property
    def source(self) -> Source:
        return Source(pdf=self.pdf, page=self.line.page)


def cpp_module(pdf: str, text: str) -> int | None:
    """The number of the C++ module the subject is (from its file name, or from its text), None for any other subject."""
    m = re.search(r"cpp(\d\d)", pdf, re.I) or re.search(r"Module\s+(\d\d)", text)
    return int(m.group(1)) if m else None
