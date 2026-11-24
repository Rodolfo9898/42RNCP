"""What the model must return: the shapes of its two answers (pydantic validates them, and they become the response schema)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CitationOut(BaseModel):
    file: str
    line: int


class ComponentOut(BaseModel):
    path: str
    role: str


class OverviewOut(BaseModel):
    purpose: str
    languages: list[str]
    build_and_run: str
    components: list[ComponentOut]
    notable: list[str]
    not_found: list[str]


class ImprovementOut(BaseModel):
    category: Literal["structure", "code", "logic", "readability"]
    priority: Literal["high", "medium", "low"]
    title: str
    detail: str
    evidence: list[CitationOut]


class AnalysisOut(BaseModel):
    overview: OverviewOut
    improvements: list[ImprovementOut]


class ReviewItemOut(BaseModel):
    rule_id: str
    assessment: Literal["likely_ok", "likely_problem", "unclear"]
    why_manual: str
    finding: str
    evidence: list[CitationOut]


class ReviewOut(BaseModel):
    items: list[ReviewItemOut]
