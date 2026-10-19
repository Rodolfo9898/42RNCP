from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Section = Literal["mandatory", "bonus"]
Status = Literal["pass", "fail", "warn", "manual", "skipped"]


class Source(BaseModel):
    pdf: str
    page: int


class Rule(BaseModel):
    """One requirement extracted from a subject.

    `kind` selects the checker. Rules without a checker (`kind == "manual"`) are
    listed in the verdict as needing a human.
    """

    id: str
    kind: str
    title: str
    text: str = ""
    section: Section = "mandatory"
    unit: str = "."  # directory, relative to the repo root, that the rule applies to
    params: dict[str, Any] = Field(default_factory=dict)
    sources: list[Source] = Field(default_factory=list)


class Evidence(BaseModel):
    file: str
    line: int | None = None
    snippet: str = ""


class CheckResult(BaseModel):
    rule_id: str | None
    title: str
    status: Status
    detail: str = ""
    section: Section = "mandatory"
    sources: list[Source] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    log: str = ""
    auto: bool = True  # False when a script could not judge it


Category = Literal["structure", "code", "logic", "readability"]
Priority = Literal["high", "medium", "low"]


class Improvement(BaseModel):
    """A suggestion to make the project better. Never affects the verdict."""

    category: Category
    title: str
    detail: str = ""
    priority: Priority = "medium"
    evidence: list[Evidence] = Field(default_factory=list)
    source: Literal["static", "ai"] = "static"


class AIComponent(BaseModel):
    path: str
    role: str


class AIOverview(BaseModel):
    purpose: str = ""
    languages: list[str] = Field(default_factory=list)
    build_and_run: str = ""
    components: list[AIComponent] = Field(default_factory=list)
    notable: list[str] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)


class AIReview(BaseModel):
    """The AI's opinion on one item a script could not check. Advisory only."""

    rule_id: str
    assessment: Literal["likely_ok", "likely_problem", "unclear", "not_applicable"]
    why_manual: str = ""
    finding: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    by: str = "AI"  # who made the assessment: "AI" (an API model) or "Claude" (the review in the terminal)


class AIEvent(BaseModel):
    at: str  # ISO timestamp
    text: str


class AIState(BaseModel):
    state: Literal["idle", "running", "done", "error", "cancelled"] = "idle"
    job: int = 0
    started_at: str = ""
    step: str = ""  # what the review is doing right now
    progress: list[AIEvent] = Field(default_factory=list)
    message: str = ""
    model: str = ""
    generated_at: str = ""
    overview: AIOverview | None = None
    reviews: dict[str, AIReview] = Field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    not_fully_sent: list[str] = Field(default_factory=list)  # files that were cut or left out of the prompt


class ReviewItem(BaseModel):
    """A requirement the scripts could not judge, numbered as in the prompt given to claude."""

    n: int
    text: str
    rule_ids: list[str] = Field(default_factory=list)


class Correction(BaseModel):
    check: str
    says: str = ""
    actually: str


class ClaudeVerdict(BaseModel):
    decision: Literal["ready to pass", "pass with reservations", "do not pass"]
    reason: str = ""


class ClaudeReport(BaseModel):
    """What was read from the structured block at the end of claude's report."""

    structured: bool = False
    corrections: list[Correction] = Field(default_factory=list)
    verdict: ClaudeVerdict | None = None
    improvements: list[Improvement] = Field(default_factory=list)
    assessed: int = 0
    total: int = 0
    problems: list[str] = Field(default_factory=list)  # why part of the report could not be used
