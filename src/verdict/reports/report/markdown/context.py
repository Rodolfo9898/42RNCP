"""What the sections of the document are written from."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from verdict.core.models import AIState, CheckResult, ClaudeReport, Improvement
from verdict.reports.report.buckets.entries import Buckets
from verdict.reports.report.buckets.sorting import bucket
from verdict.reports.report.summary.corrections import corrected
from verdict.reports.report.summary.result import summarize


@dataclass
class ReportContext:
    """Everything a section may need, worked out once: the result, and the results sorted into the buckets of each part."""

    repo: dict | None
    subjects: list[str]
    results: list[CheckResult]
    improvements: list[Improvement]
    readme: dict | None
    ai: AIState | None
    claude_review: str
    claude: ClaudeReport
    project: str
    summary: dict
    mandatory: Buckets
    bonus: Buckets

    @classmethod
    def of(cls, *, repo: dict | None, subjects: list[str], results: list[CheckResult], improvements: list[Improvement] | None = None,
           readme: dict | None = None, ai: AIState | None = None, claude_review: str = "", claude: ClaudeReport | None = None,
           project: str = "") -> ReportContext:
        claude = claude or ClaudeReport()
        shown = corrected(results, claude)
        return cls(repo, subjects, results, improvements or [], readme, ai, claude_review, claude, project,
                   summarize(results, ai, claude),
                   bucket([r for r in shown if r.section == "mandatory"], ai), bucket([r for r in shown if r.section == "bonus"], ai))

    @property
    def merged(self) -> bool:
        """claude's answers are in the buckets; its prose is not repeated."""
        return self.claude.structured

    @property
    def lacking(self) -> int:
        return len(self.mandatory.lacking)

    @property
    def second(self) -> int:
        return len(self.mandatory.second)

    @property
    def ok(self) -> int:
        return len(self.mandatory.ok) + len(self.mandatory.not_applicable)


class Section(ABC):
    """One part of the document: the lines it adds (none when it has nothing to say)."""

    @abstractmethod
    def render(self, ctx: ReportContext) -> list[str]: ...
