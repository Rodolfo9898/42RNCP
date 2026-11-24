"""An update laid over the previous report.

A block with a "fixes" key (or without "items") is written after claude fixed something or settled points with the evaluator:
it only has to say what changed, and the rest stays as the previous report had it."""

from __future__ import annotations

from verdict.core.models import AIReview, ClaudeReport, ClaudeVerdict, Correction, Fix, Improvement, ReviewItem
from verdict.reviews.claude_report.vocabulary import norm


class UpdateLayer:
    """What an update replaces in `previous` and what it leaves alone."""

    def __init__(self, previous: ClaudeReport, previous_reviews: dict[str, AIReview] | None):
        self.previous, self.previous_reviews = previous, previous_reviews or {}

    def reviews(self, reviews: dict[str, AIReview], answered: set[int], items: list[ReviewItem]) -> tuple[dict[str, AIReview], set[int]]:
        merged = {**self.previous_reviews, **reviews}
        return merged, answered | {item.n for item in items if any(rule_id in merged for rule_id in item.rule_ids)}

    def known_improvements(self) -> set[str]:
        return {norm(i.title) for i in self.previous.improvements}

    def merged(self, corrections: list[Correction], fixes: list[Fix], verdict: ClaudeVerdict | None, improvements: list[Improvement],
               improvements_given: bool) -> tuple[list[Correction], list[Fix], ClaudeVerdict | None, list[Improvement]]:
        corrections = list({norm(c.check): c for c in [*self.previous.corrections, *corrections]}.values())   # the latest word on each
        fixes = list({norm(f.issue): f for f in [*self.previous.fixes, *fixes]}.values())
        if not improvements_given:
            improvements = [i.model_copy(update={"new": False}) for i in self.previous.improvements]
        return corrections, fixes, verdict or self.previous.verdict, improvements
