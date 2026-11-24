"""How one entry, and a titled list of entries, is written."""

from __future__ import annotations

from verdict.reports.report.buckets.entries import Entry
from verdict.reports.report.markdown.text import code, evidence_line, fenced, inline, sources, where


def entry_lines(e: Entry, *, compact: bool = False) -> list[str]:
    tag = "" if e.by == "script" else f" `{e.by}`"
    head = inline(e.title)
    if compact:
        line = f"- {head}" + (f" — {inline(e.detail)}" if e.detail else "") + (f" {code(where(e.evidence[0]))}" if e.evidence else "")
        return [line + tag]
    lines = [f"- **{head}**{tag}" + (f" — {inline(e.detail)}" if e.detail else "") + sources(e.sources)]
    if e.check_by_hand:
        lines.append(f"  - _Check by hand:_ {inline(e.check_by_hand)}")
    lines += [evidence_line(ev) for ev in e.evidence[:6]]
    if e.log:
        lines += ["", *("    " + l for l in fenced(e.log[-1200:])), ""]
    return lines


def section(title: str, entries: list[Entry], intro: str = "", *, compact: bool = False) -> list[str]:
    if not entries:
        return []
    out = [f"### {title} ({len(entries)})", ""]
    if intro:
        out += [intro, ""]
    for e in entries:
        out += entry_lines(e, compact=compact)
    return out + [""]
