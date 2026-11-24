"""The end of the document: the result, what to do next, and what is still open."""

from __future__ import annotations

from verdict.reports.report.markdown.context import ReportContext, Section
from verdict.reports.report.markdown.text import inline

MAX_TODO = 8


class FinalVerdictSection(Section):
    def render(self, ctx: ReportContext) -> list[str]:
        summary, claude = ctx.summary, ctx.claude
        overall, decided = summary["overall"], summary["decided_by"] == "claude"
        out = ["## Final verdict", "", f"**Result: {overall}**" + (f" · **Claude: {claude.verdict.decision}**" if decided else ""), ""]
        if decided:
            out += ["Claude has the final say" + ("" if summary["lists"] == overall else f": the lists above alone would say {summary['lists']}") + ".", ""]
        if summary["reason"]:
            out += [f"> {inline(summary['reason'])}", ""]
        if overall == "NOT RUN":
            return out + ["The checks have not been run yet.", ""]
        out += self._next_steps(ctx)
        out += self._still_open(ctx)
        if claude.problems and claude.structured:
            out += ["_Notes on claude's report: " + " ".join(inline(p) for p in claude.problems[:3]) + "_", ""]
        out.append(self._claude_answer(ctx))
        return out + ["", "_These results come from scripts and claude's review; the peer evaluation decides the grade._", ""]

    @staticmethod
    def _next_steps(ctx: ReportContext) -> list[str]:
        todo = ctx.mandatory.lacking
        if todo:
            out = [f"What to do next ({len(todo)} thing(s) lacking, most important first):", ""]
            out += [f"{n}. {inline(e.title)}" + (f" — {inline(e.detail)}" if e.detail else "") for n, e in enumerate(todo[:MAX_TODO], 1)]
            if len(todo) > MAX_TODO:
                out.append(f"{len(todo)}. … and {len(todo) - MAX_TODO} more (listed above)")
            return out + [""]
        if ctx.summary["overall"] == "FAIL":
            return ["Nothing is listed as lacking, but Claude decided this does not pass: see its reason above.", ""]
        if ctx.summary["lists"] == "PASS":
            return ["Nothing is lacking and nothing needs a second look.", ""]
        return ["Nothing is lacking.", ""]

    @staticmethod
    def _still_open(ctx: ReportContext) -> list[str]:
        still = []
        if ctx.mandatory.second:
            still.append(f"{len(ctx.mandatory.second)} point(s) for a second look")
        if ctx.mandatory.unreviewed:
            still.append(f"{len(ctx.mandatory.unreviewed)} requirement(s) nobody has assessed yet")
        return ["Still open: " + "; ".join(still) + ".", ""] if still else []

    @staticmethod
    def _claude_answer(ctx: ReportContext) -> str:
        if ctx.claude.structured:
            return f"Claude answered {ctx.claude.assessed} of {ctx.claude.total} requirement(s)."
        if ctx.claude_review.strip():
            return "Claude's report is included above as text (it could not be merged into the lists)."
        return "Claude has not reviewed what the scripts could not check (use AI Review in the Verdict view, then Merge claude's Review)."
