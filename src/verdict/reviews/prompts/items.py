"""What the review prompt lists: the requirements nobody could check by script, and what the checks said."""

from __future__ import annotations

from verdict.core.models import CheckResult, ReviewItem
from verdict.reviews.prompts.text import short

MAX_ITEMS = 60
MAX_ITEM_CHARS = 400
MAX_LISTED = 40


def manual_items(results: list[CheckResult]) -> list[ReviewItem]:
    """The requirements the scripts could not judge, numbered 1..n exactly as the prompt shows them.
    Identical sentences (the same rule from several subjects) share one number."""
    by_sentence: dict[str, ReviewItem] = {}
    for r in results:
        if r.status != "manual":
            continue
        sentence = short(r.detail or r.title, MAX_ITEM_CHARS)
        source = f" ({r.sources[0].pdf} p.{r.sources[0].page})" if r.sources else ""
        item = by_sentence.setdefault(sentence, ReviewItem(n=len(by_sentence) + 1, text=sentence + source))
        if r.rule_id and r.rule_id not in item.rule_ids:
            item.rule_ids.append(r.rule_id)
    return list(by_sentence.values())[:MAX_ITEMS]


def titles(results: list[CheckResult], status: str, limit: int = MAX_LISTED) -> list[str]:
    """The titles of the results with this status (with their detail when it is not a pass), once each, at most `limit`."""
    seen: dict[str, None] = {}
    for r in results:
        if r.status == status:
            seen.setdefault(short(r.title + (f": {r.detail}" if status != "pass" and r.detail else ""), 200))
    items = list(seen)
    return items[:limit] + ([f"… and {len(items) - limit} more"] if len(items) > limit else [])
