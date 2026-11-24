"""The result of a review: the verdict as the lists say it, and as claude decides it."""

from __future__ import annotations

from collections import Counter

from verdict.core.models import AIState, CheckResult, ClaudeReport
from verdict.reports.report.buckets.sorting import bucket
from verdict.reports.report.summary.corrections import corrected
from verdict.reports.report.summary.status import shown_status

ORDER = ("fail", "warn", "manual", "skipped", "na", "pass")
# claude's decision, as the result it stands for. Once its report is merged, claude has the final say.
CLAUDE_DECIDES = {"ready to pass": "PASS", "pass with reservations": "PASS WITH ISSUES", "do not pass": "FAIL"}


def lists_verdict(shown: list[CheckResult], ai: AIState | None) -> str:
    """What the two lists of verdict.md (mandatory part) say: anything under "Lacking" is a FAIL; otherwise anything under
    "Second look" is a PASS WITH ISSUES; otherwise PASS."""
    mandatory = bucket([r for r in shown if r.section == "mandatory"], ai)
    if mandatory.lacking:
        return "FAIL"
    return "PASS WITH ISSUES" if mandatory.second else "PASS"


def summarize(results: list[CheckResult], ai: AIState | None = None, claude: ClaudeReport | None = None) -> dict:
    """Before claude's review is merged the result follows the two lists of verdict.md (mandatory part): anything under
    "Lacking" is a FAIL; otherwise anything under "Second look" is a PASS WITH ISSUES; otherwise PASS. After the merge claude
    has the final say: its decision (ready to pass / pass with reservations / do not pass) is the result, and `lists` keeps
    what the lists alone would have said. The counts and the lists read what claude found, not what it overwrote."""
    shown = corrected(results, claude)
    counts = {sec: Counter(shown_status(r, ai) for r in shown if r.section == sec) for sec in ("mandatory", "bonus")}
    lists = lists_verdict(shown, ai) if results else "NOT RUN"
    decision = claude.verdict.decision if claude is not None and claude.verdict is not None else None
    final = CLAUDE_DECIDES.get(decision) if results and decision else None
    m = counts["mandatory"]
    return {
        "overall": final or lists,
        "decided_by": "claude" if final else "scripts",
        "lists": lists,
        "reason": claude.verdict.reason if final else "",
        "mandatory": {s: m[s] for s in ORDER},
        "bonus": {s: counts["bonus"][s] for s in ORDER},
    }
