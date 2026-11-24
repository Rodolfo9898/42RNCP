"""The top of the document: the headline, where the repository came from, and the counts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from shared.constants import VERDICT_MARKER
from verdict.reports.report.markdown.context import ReportContext, Section
from verdict.reports.report.markdown.text import code, inline


class HeadlineSection(Section):
    def render(self, ctx: ReportContext) -> list[str]:
        out = [VERDICT_MARKER, "", f"# Verdict{': ' + inline(ctx.project) if ctx.project else ''}", ""]
        if not ctx.results:
            return out + ["**NOT RUN** — the checks have not been run yet.", ""]
        summary = ctx.summary
        icon = {"FAIL": "❌", "PASS WITH ISSUES": "⚠️"}.get(summary["overall"], "✅")
        headline = f"{icon} **{summary['overall']}**"
        if summary["decided_by"] == "claude":
            headline += f" · decided by Claude: **{ctx.claude.verdict.decision}**"
            if summary["lists"] != summary["overall"]:
                headline += f" (the lists below alone say {summary['lists']})"
        out += [headline, ""]
        if summary["reason"]:
            out += [f"> {inline(summary['reason'])}", ""]
        bonus = ctx.bonus
        part = " (mandatory part)" if bonus.ok or bonus.lacking or bonus.second else ""
        return out + [f"{ctx.lacking} thing(s) lacking · {ctx.second} to look at a second time · {ctx.ok} ok{part}", ""]


class ProvenanceSection(Section):
    """The repository and the subjects the verdict is about, and when it was made."""

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.clock = clock

    def render(self, ctx: ReportContext) -> list[str]:
        out: list[str] = []
        if ctx.repo:
            out.append(f"- Repository: {inline(ctx.repo['url'])}")
            out.append(f"- Commit: {code(ctx.repo['commit'])} {inline(ctx.repo.get('subject', ''))} ({inline(ctx.repo.get('author', ''))})")
        out.append("- Subjects: " + (", ".join(inline(x) for x in ctx.subjects) or "none"))
        out.append(f"- Generated: {self.clock():%Y-%m-%d %H:%M UTC}")
        return out + [""]


class AtAGlanceSection(Section):
    def render(self, ctx: ReportContext) -> list[str]:
        bonus = ctx.bonus
        out = ["## At a glance", "", "| | ❌ Lacking | ⚠️ Second look | ✅ Ok |", "|---|---:|---:|---:|",
               f"| Mandatory part | {ctx.lacking} | {ctx.second} | {ctx.ok} |"]
        if any((bonus.lacking, bonus.second, bonus.ok, bonus.not_applicable)):
            out.append(f"| Bonus part | {len(bonus.lacking)} | {len(bonus.second)} | {len(bonus.ok) + len(bonus.not_applicable)} |")
        return out + ["", "> FAIL when anything is lacking, PASS WITH ISSUES when something still needs a second look, PASS when both "
                         "lists are empty. Once claude's review is merged, claude has the final say: ready to pass is PASS, pass with "
                         "reservations is PASS WITH ISSUES, do not pass is FAIL; and what it found replaces what the scripts reported. "
                         "Items marked `Claude` were assessed by claude in the terminal. The peer evaluation decides the grade.", ""]
