"""What claude wrote: the fixes it made, and its free-form report when its structured block could not be merged."""

from __future__ import annotations

import re

from verdict.reports.report.markdown.context import ReportContext, Section
from verdict.reports.report.markdown.text import code, inline, where

FIX_ICONS = {"fixed": "✅", "not fixed": "❌", "not a real problem": "➖"}


class FixesSection(Section):
    """What claude corrected after the review, and whether doing so turned up anything new to improve."""

    def render(self, ctx: ReportContext) -> list[str]:
        claude = ctx.claude
        if not claude.fixes:
            return []
        out = [f"## 🛠 What Claude corrected ({len(claude.fixes)})", ""]
        for f in claude.fixes:
            out.append(f"- {FIX_ICONS[f.status]} **{inline(f.issue)}** — {f.status}" + (f": {inline(f.detail)}" if f.detail else ""))
            out += [f"  - {code(where(e))}" for e in f.evidence[:6]]
        out.append("")
        new = [i for i in claude.improvements if i.new]
        if new:
            return out + [f"**New improvements found ({len(new)}):** " + "; ".join(inline(i.title) for i in new) + " (🆕 under Improvements).", ""]
        return out + ["**New improvements found:** none.", ""]


class ClaudeProseSection(Section):
    """claude's free-form report, used only when its structured block could not be merged. It was written about untrusted
    code, so it is treated as untrusted text: markup defused, headings demoted, length capped, an open fence closed."""

    def render(self, ctx: ReportContext) -> list[str]:
        if not ctx.claude_review.strip() or ctx.merged:
            return []
        out: list[str] = []
        if ctx.claude.problems:
            out += ["> ⚠ claude's report could not be merged into the lists above: " + " ".join(inline(p) for p in ctx.claude.problems[:2]), ""]
        out += ["## Claude's review (from the terminal)", "",
                "> Written by claude in the terminal, advisory and unverified. It never changes the result above.", ""]
        return out + self._body(ctx.claude_review) + [""]

    @staticmethod
    def _body(text: str) -> list[str]:
        out: list[str] = []
        fence = ""
        for raw in text[:100_000].splitlines():
            line = raw.rstrip()
            marker = re.match(r"\s*(`{3,}|~{3,})", line)
            if marker and not fence:
                fence = marker.group(1)
                out.append(line)
            elif marker and fence and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence) and not line.strip().strip("`~"):
                fence = ""
                out.append(line)
            elif fence:
                out.append(line)
            else:
                line = re.sub(r"<", r"\\<", line)
                heading = re.match(r"(#{1,6})\s+(.*)", line)
                out.append(f"{'#' * min(6, len(heading.group(1)) + 2)} {heading.group(2)}" if heading else line)
        if fence:
            out.append(fence)
        return out
