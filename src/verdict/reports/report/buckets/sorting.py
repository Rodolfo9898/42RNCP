"""Sorting everything into the buckets verdict.md is made of."""

from __future__ import annotations

from verdict.core.models import AIState, CheckResult
from verdict.reports.report.buckets.entries import Buckets, Entry

# Where a requirement that was assessed goes, by what the assessment says.
ASSESSED_INTO = {"likely_problem": "lacking", "unclear": "second", "likely_ok": "ok", "not_applicable": "not_applicable"}
# Where a check that ran goes, by its status (a warning or a skipped check is for a second look, or a bonus that was not submitted).
CHECKED_INTO = {"fail": "lacking", "warn": "second", "skipped": "second", "pass": "ok", "na": "not_applicable"}


class Bucketer:
    """Sorts check results into lacking / second look / ok / not applicable: a check goes by its status, a requirement a script
    could not judge goes by what the AI or claude said about it (and to 'not reviewed yet' when nobody did)."""

    def __init__(self, ai: AIState | None) -> None:
        self.ai = ai
        self.out = Buckets()
        self.seen: set[str] = set()

    def sort(self, results: list[CheckResult]) -> Buckets:
        for r in results:
            if r.status == "manual":
                self._requirement(r)
            else:
                self._check(r)
        return self.out

    def _requirement(self, r: CheckResult) -> None:
        text = r.detail or r.title
        if text in self.seen:                       # the same sentence from two subjects is one requirement
            return
        self.seen.add(text)
        review = self.ai.reviews.get(r.rule_id) if self.ai and r.rule_id else None
        if review is None:
            entry = Entry(text, "not reviewed yet: a human has to judge this", sources=r.sources, requirement=True)
            self.out.second.append(entry)
            self.out.unreviewed.append(entry)
            return
        entry = Entry(text, review.finding, by=review.by, sources=r.sources, evidence=review.evidence,
                      check_by_hand=review.why_manual, requirement=True)
        getattr(self.out, ASSESSED_INTO[review.assessment]).append(entry)

    def _check(self, r: CheckResult) -> None:
        entry = Entry(r.title, r.detail, by=r.by, sources=r.sources, evidence=r.evidence, log=r.log if r.status in ("fail", "warn") else "")
        target = CHECKED_INTO.get(r.status)
        if r.status in ("warn", "skipped") and r.title.startswith("Bonus part not submitted"):
            target = "not_submitted"
        if target:
            getattr(self.out, target).append(entry)


def bucket(results: list[CheckResult], ai: AIState | None) -> Buckets:
    return Bucketer(ai).sort(results)
