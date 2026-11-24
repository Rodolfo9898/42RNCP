"""The numbered answers of the block: one per requirement the prompt listed."""

from __future__ import annotations

from verdict.core.models import AIReview, ReviewItem
from verdict.reviews.claude_report.evidence import citations
from verdict.reviews.claude_report.vocabulary import STATUS, norm, text


class ItemAnswers:
    """Turns the "items" of the block into assessments by rule id. Unknown numbers are ignored, unknown statuses become "unclear"."""

    def __init__(self, items: list[ReviewItem], files: dict[str, int], problems: list[str]):
        self.by_number = {item.n: item for item in items}
        self.files, self.problems = files, problems

    def read(self, raw: list) -> tuple[dict[str, AIReview], set[int]]:
        """(reviews by rule id, the numbers that were answered)."""
        reviews: dict[str, AIReview] = {}
        answered: set[int] = set()
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            number = self._number(entry)
            if number is None:
                continue
            item = self.by_number.get(number)
            if item is None:
                self.problems.append(f"Item {number} does not exist in the prompt and was ignored.")
                continue
            status = self._status(number, entry)
            answered.add(number)
            for rule_id in item.rule_ids:
                reviews[rule_id] = AIReview(
                    rule_id=rule_id, assessment=status, finding=text(entry.get("note"), 700),
                    why_manual=text(entry.get("check_by_hand"), 400), evidence=citations(entry.get("evidence"), self.files), by="Claude")
        return reviews, answered

    def _number(self, entry: dict) -> int | None:
        try:
            return int(entry.get("n"))
        except (TypeError, ValueError):
            self.problems.append(f"An item without a usable number was ignored: {text(entry, 60)!r}.")
            return None

    def _status(self, number: int, entry: dict) -> str:
        status = STATUS.get(norm(entry.get("status")))
        if status is None:
            self.problems.append(f"Item {number} has an unknown status {text(entry.get('status'), 30)!r}; treated as unclear.")
            return "unclear"
        return status

    def missing(self, answered: set[int]) -> str | None:
        """The problem to report when some requirements got no answer, or None."""
        missing = sorted(set(self.by_number) - answered)
        if not missing:
            return None
        return (f"Claude did not answer {len(missing)} of {len(self.by_number)} requirement(s): "
                f"{', '.join('#' + str(n) for n in missing[:12])}{'…' if len(missing) > 12 else ''}. They stay under 'second look'.")
