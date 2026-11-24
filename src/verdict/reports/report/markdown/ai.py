"""What the AI said about the repository, and the improvements to make."""

from __future__ import annotations

from verdict.reports.report.markdown.context import ReportContext, Section
from verdict.reports.report.markdown.text import code, evidence_line, inline

AI_NOTE = ("> Written by an AI model ({model}) from a bounded view of the repository. It is advisory and unverified: "
           "it never changes the result, and file/line citations are checked against what the model was shown.")
CATEGORY_TITLES = {"structure": "Structure", "code": "Code", "logic": "Logic", "readability": "Readability"}


class AiOverviewSection(Section):
    def render(self, ctx: ReportContext) -> list[str]:
        ai = ctx.ai
        if not (ai and ai.state == "done" and ai.overview):
            return []
        ov = ai.overview
        out = ["## What is in the repository (AI)", "", AI_NOTE.format(model=inline(ai.model)), ""]
        if ov.purpose:
            out += [f"**Purpose:** {inline(ov.purpose)}", ""]
        if ov.languages:
            out += [f"**Languages:** {', '.join(inline(x) for x in ov.languages)}", ""]
        if ov.build_and_run:
            out += [f"**Build and run:** {inline(ov.build_and_run)}", ""]
        if ov.components:
            out += ["| Path | Role |", "|---|---|"]
            out += [f"| {code(c.path)} | {inline(c.role)} |" for c in ov.components]
            out.append("")
        if ov.notable:
            out += ["**Notable:**", ""] + [f"- {inline(x)}" for x in ov.notable] + [""]
        if ov.not_found:
            out += ["**Required by the subject but not found:**", ""] + [f"- {inline(x)}" for x in ov.not_found] + [""]
        if ai.not_fully_sent:
            out += [f"_{len(ai.not_fully_sent)} file(s) were cut or left out of what the model saw: "
                    f"{', '.join(inline(f) for f in ai.not_fully_sent[:6])}{'…' if len(ai.not_fully_sent) > 6 else ''}._", ""]
        return out


class ImprovementsSection(Section):
    def render(self, ctx: ReportContext) -> list[str]:
        by_claude = ctx.merged and bool(ctx.claude.improvements)
        out = ["## Improvements", "",
               "> Suggestions for making the project better" + (", from claude's review" if by_claude else ", from heuristics")
               + ". They never change the result above.", ""]
        out += self._readme(ctx.readme)
        if not ctx.improvements:
            return out + ["No improvement suggestions.", ""]
        for category, heading in CATEGORY_TITLES.items():
            items = [i for i in ctx.improvements if i.category == category]
            if items:
                out += [f"### {heading} ({len(items)})", ""]
                for i in items:
                    out += self._improvement(i, by_claude)
                out.append("")
        return out

    @staticmethod
    def _readme(readme: dict | None) -> list[str]:
        if readme is None:
            return []
        if readme.get("present"):
            return [f"**README:** {code(readme['name'])} found ({readme['lines']} non-empty lines).", ""]
        return ["**README:** ⚠ **no README found** in the repository.", ""]

    @staticmethod
    def _improvement(i, by_claude: bool) -> list[str]:
        tag = " _(AI)_" if i.source == "ai" and not by_claude else ""
        out = [f"- **[{i.priority}] {inline(i.title)}**{tag}" + (" 🆕" if i.new else "") + (f" — {inline(i.detail)}" if i.detail else "")]
        out += [evidence_line(e) for e in i.evidence[:8]]
        if len(i.evidence) > 8:
            out.append(f"  - … and {len(i.evidence) - 8} more")
        return out
