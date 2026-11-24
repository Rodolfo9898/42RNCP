"""How a requirement that was judged is counted, and what a result becomes once claude has overwritten it."""

from __future__ import annotations

from verdict.core.models import AIState, CheckResult

# Where a requirement that claude (or the AI) has judged is counted: the same place verdict.md lists it.
REVIEWED_STATUS = {"likely_problem": "fail", "unclear": "manual", "likely_ok": "pass", "not_applicable": "pass"}
# What a result becomes once claude has overwritten it.
CORRECTED_STATUS = {"likely_problem": "fail", "unclear": "warn", "likely_ok": "pass", "not_applicable": "na"}


def shown_status(r: CheckResult, ai: AIState | None) -> str:
    review = ai.reviews.get(r.rule_id) if ai and r.status == "manual" and r.rule_id else None
    return REVIEWED_STATUS.get(review.assessment, "manual") if review else r.status
