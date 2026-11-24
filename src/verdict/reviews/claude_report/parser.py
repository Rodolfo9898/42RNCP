"""Read the structured block at the end of claude's report and turn it into assessments for the verdict.

claude writes a free-form report (kept as claude-review.md) and ends it with one fenced json block. Only that block is
merged into verdict.md, so the document stays one readable page instead of two. Everything in it is checked: unknown
requirement numbers are ignored, and a cited file or line that does not exist is dropped rather than shown.
"""

from __future__ import annotations

from verdict.core.models import AIReview, ClaudeReport, ReviewItem
from verdict.reviews.claude_report.blocks import extract_block
from verdict.reviews.claude_report.entries import ReportEntries
from verdict.reviews.claude_report.items import ItemAnswers
from verdict.reviews.claude_report.layering import UpdateLayer
from verdict.reviews.claude_report.vocabulary import norm


class ReportParser:
    """Reads one report against the numbered items of its prompt and the files that exist. An update (a block with "fixes")
    is laid over `previous`: what it says replaces what was there, and what it leaves out stays."""

    NO_BLOCK = ("The report has no json block at the end, so it could not be merged. "
                "Ask claude to add it (the shape is in the prompt).")

    def __init__(self, items: list[ReviewItem], files: dict[str, int], previous: ClaudeReport | None = None,
                 previous_reviews: dict[str, AIReview] | None = None):
        self.items, self.files = items, files
        self.previous, self.previous_reviews = previous, previous_reviews

    def parse(self, markdown: str) -> tuple[ClaudeReport, dict[str, AIReview]]:
        """Returns (report, reviews by rule id). `report.structured` is False when nothing usable was found."""
        data = extract_block(markdown)
        if data is None:
            return ClaudeReport(total=len(self.items), problems=[self.NO_BLOCK]), {}
        problems: list[str] = []
        answers = ItemAnswers(self.items, self.files, problems)
        reviews, answered = answers.read(data.get("items") or [])
        is_update = "fixes" in data or "items" not in data     # a block that answers no requirement can only be an update
        layer = UpdateLayer(self.previous, self.previous_reviews) if is_update and self.previous is not None and self.previous.structured else None
        if layer:
            reviews, answered = layer.reviews(reviews, answered, self.items)
        if (missing := answers.missing(answered)) is not None:
            problems.append(missing)

        entries = ReportEntries(self.files, problems)
        corrections = entries.corrections(data.get("corrections"))
        fixes = entries.fixes(data.get("fixes"))
        improvements = entries.improvements(data.get("improvements"))
        verdict = entries.verdict(data.get("verdict"))
        if is_update:
            known = layer.known_improvements() if layer else set()
            for improvement in improvements:
                improvement.new = norm(improvement.title) not in known
        if layer:
            corrections, fixes, verdict, improvements = layer.merged(corrections, fixes, verdict, improvements, "improvements" in data)
        report = ClaudeReport(structured=True, corrections=corrections, fixes=fixes, verdict=verdict, improvements=improvements,
                              assessed=len(answered), total=len(answers.by_number), problems=problems)
        return report, reviews


def parse_report(markdown: str, items: list[ReviewItem], files: dict[str, int], previous: ClaudeReport | None = None,
                 previous_reviews: dict[str, AIReview] | None = None) -> tuple[ClaudeReport, dict[str, AIReview]]:
    return ReportParser(items, files, previous, previous_reviews).parse(markdown)
