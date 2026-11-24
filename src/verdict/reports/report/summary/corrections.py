"""What claude found different replaces what a script said."""

from __future__ import annotations

from verdict.core.models import CheckResult, ClaudeReport, Correction
from verdict.reports.report.summary.status import CORRECTED_STATUS


def normalize(text: str) -> str:
    return " ".join(text.replace("`", "").split()).casefold()


def names(check: str, name: str) -> bool:
    """Does what claude wrote name this result? The prompts print `title: detail` or `title — detail`, and may cut long titles."""
    wanted, known = normalize(check), normalize(name)
    if not wanted or not known:
        return False
    if wanted == known or wanted.startswith((known + ":", known + " —")):
        return True
    return wanted.endswith("…") and known.startswith(wanted[:-1])


def named(check: str, r: CheckResult) -> bool:
    return names(check, r.title) or (r.status == "manual" and names(check, r.detail))


class Corrector:
    """Lays claude's corrections over the results of the scripts: a result a correction names is replaced by what claude says, and a
    correction about nothing known is added as a finding. The scripts' own results are never touched."""

    def __init__(self, claude: ClaudeReport) -> None:
        self.claude = claude

    def apply(self, results: list[CheckResult]) -> list[CheckResult]:
        out = list(results)
        for c in self.claude.corrections:
            self._one(out, c)
        return self._without_repeats(out)

    @staticmethod
    def _replacement(c: Correction) -> dict:
        return {"status": CORRECTED_STATUS[c.status], "detail": c.actually, "evidence": c.evidence, "log": "", "by": "Claude", "auto": True}

    def _one(self, out: list[CheckResult], c: Correction) -> None:
        matches = [i for i, r in enumerate(out) if r.by == "script" and named(c.check, r)]
        replacement = self._replacement(c)
        for i in matches:
            r = out[i]
            title = " ".join((r.detail or r.title).split()) if r.status == "manual" else r.title
            out[i] = r.model_copy(update={**replacement, "title": title})
        if not matches:
            out.append(CheckResult(rule_id=None, title=c.check or "Claude's finding", section=c.section, **replacement))

    @staticmethod
    def _without_repeats(results: list[CheckResult]) -> list[CheckResult]:
        """The same sentence from two subjects is one requirement, so once overwritten it is listed once."""
        seen: set[str] = set()
        out = []
        for r in results:
            key = normalize(r.title)
            if r.by != "script" and key in seen:
                continue
            if r.by != "script":
                seen.add(key)
            out.append(r)
        return out


def corrected(results: list[CheckResult], claude: ClaudeReport | None) -> list[CheckResult]:
    """The results as the whole evaluation reads them: what claude found different replaces the script's statement, and a
    finding about nothing known is added. `results` itself keeps what the scripts said."""
    if claude is None or not claude.corrections:
        return results
    return Corrector(claude).apply(results)
