from __future__ import annotations

from dataclasses import dataclass, field

from verdict.core.models import Rule, Section


@dataclass
class Line:
    text: str
    page: int
    section: Section
    chapter: str


@dataclass
class Spec:
    name: str
    lang: str | None = None  # "c" | "cpp" | None
    rules: list[Rule] = field(default_factory=list)
