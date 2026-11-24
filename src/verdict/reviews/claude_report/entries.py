"""The entries of the block other than the numbered items: corrections, fixes, improvements and the verdict."""

from __future__ import annotations

from verdict.core.models import ClaudeVerdict, Correction, Fix, Improvement
from verdict.reviews.claude_report.evidence import citations
from verdict.reviews.claude_report.vocabulary import CATEGORIES, DECISION, FIX_STATUS, PRIORITIES, STATUS, norm, text


class ReportEntries:
    """Reads the lists of the block into the models, checking every citation against `files` and noting in `problems`
    what had to be guessed."""

    def __init__(self, files: dict[str, int], problems: list[str]):
        self.files, self.problems = files, problems

    def corrections(self, raw: object) -> list[Correction]:
        out: list[Correction] = []
        for entry in raw if isinstance(raw, list) else []:
            if not isinstance(entry, dict) or not entry.get("actually"):
                continue
            check = text(entry.get("check"), 240)
            status = STATUS.get(norm(entry.get("status")))
            if status is None:
                self.problems.append(f"The correction of {check!r} has no usable status; it is listed under 'second look'.")
            out.append(Correction(check=check, says=text(entry.get("says"), 300), actually=text(entry.get("actually"), 500),
                                  status=status or "unclear", evidence=citations(entry.get("evidence"), self.files),
                                  section="bonus" if norm(entry.get("section")) == "bonus" else "mandatory"))
        return out

    def fixes(self, raw: object) -> list[Fix]:
        return [Fix(issue=text(entry.get("issue"), 240), status=FIX_STATUS.get(norm(entry.get("status")), "fixed"),
                    detail=text(entry.get("detail"), 600), evidence=citations(entry.get("evidence"), self.files))
                for entry in (raw if isinstance(raw, list) else []) if isinstance(entry, dict) and entry.get("issue")]

    def improvements(self, raw: object) -> list[Improvement]:
        out: list[Improvement] = []
        for entry in raw or []:
            if not isinstance(entry, dict) or not entry.get("title"):
                continue
            category, priority = norm(entry.get("category")), norm(entry.get("priority"))
            out.append(Improvement(
                category=category if category in CATEGORIES else "code", priority=priority if priority in PRIORITIES else "medium",
                title=text(entry.get("title"), 140), detail=text(entry.get("detail"), 600),
                evidence=citations(entry.get("evidence"), self.files), source="ai"))
        return out

    def verdict(self, raw: object) -> ClaudeVerdict | None:
        if isinstance(raw, dict) and DECISION.get(norm(raw.get("decision"))):
            return ClaudeVerdict(decision=DECISION[norm(raw["decision"])], reason=text(raw.get("reason"), 600))
        if raw:
            self.problems.append("The verdict in the block was not one of: ready to pass, pass with reservations, do not pass.")
        return None
