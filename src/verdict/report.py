"""Aggregate check results into a verdict and render verdict.md.

verdict.md is ONE page that answers three questions, whoever found the answer (a script, or claude's review):

  ❌ what is lacking       -> fix these
  ⚠  what needs a second look -> a human should verify these
  ✅ what is ok            -> nothing to do

Only the structured answers of claude's report are merged here; its prose is kept in the session, not in the repository.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .checks import VERDICT_MARKER
from .models import AIReview, AIState, CheckResult, ClaudeReport, Evidence, Improvement

ORDER = ("fail", "warn", "manual", "skipped", "pass")
AI_NOTE = ("> Written by an AI model ({model}) from a bounded view of the repository. It is advisory and unverified: "
           "it never changes the result, and file/line citations are checked against what the model was shown.")
CATEGORY_TITLES = {"structure": "Structure", "code": "Code", "logic": "Logic", "readability": "Readability"}


# Where a requirement that claude (or the AI) has judged is counted: the same place verdict.md lists it.
REVIEWED_STATUS = {"likely_problem": "fail", "unclear": "manual", "likely_ok": "pass", "not_applicable": "pass"}


def shown_status(r: CheckResult, ai: AIState | None) -> str:
    review = ai.reviews.get(r.rule_id) if ai and r.status == "manual" and r.rule_id else None
    return REVIEWED_STATUS.get(review.assessment, "manual") if review else r.status


def summarize(results: list[CheckResult], ai: AIState | None = None, claude: ClaudeReport | None = None) -> dict:
    """The result follows the two lists of verdict.md (mandatory part, claude's answers included):
    anything under "Lacking" is a FAIL; otherwise anything under "Second look" is a PASS WITH ISSUES; otherwise PASS."""
    counts = {sec: Counter(shown_status(r, ai) for r in results if r.section == sec) for sec in ("mandatory", "bonus")}
    if not results:
        overall = "NOT RUN"
    else:
        mandatory = bucket([r for r in results if r.section == "mandatory"], ai)
        if mandatory.lacking:
            overall = "FAIL"
        elif mandatory.second or (claude is not None and claude.corrections):
            overall = "PASS WITH ISSUES"
        else:
            overall = "PASS"
    m = counts["mandatory"]
    return {
        "overall": overall,
        "mandatory": {s: m[s] for s in ORDER},
        "bonus": {s: counts["bonus"][s] for s in ORDER},
    }


# --------------------------------------------------------------------------- text helpers (results carry repo-controlled strings)


def _code(text: str) -> str:
    text = " ".join(str(text).split())
    return f"`` {text} ``" if "`" in text else f"`{text}`"


def _inline(text: str) -> str:
    """Single-line, markdown-neutral text. Balanced `code spans` are kept; everything else is escaped."""
    text = " ".join(text.split())
    parts = re.split(r"(`[^`]+`)", text)
    return "".join(
        part if len(part) > 2 and part.startswith("`") and part.endswith("`")
        else re.sub(r"([\\*_\[\]<>|`])", r"\\\1", part)
        for part in parts
    )


def _where(e: Evidence) -> str:
    return f"{e.file}:{e.line}" if e.line else e.file


def _sources(sources) -> str:
    return " _(" + ", ".join(f"{_inline(s.pdf)} p.{s.page}" for s in sources[:3]) + ")_" if sources else ""


# --------------------------------------------------------------------------- sorting everything into the three buckets


@dataclass
class Entry:
    title: str
    detail: str = ""
    by: str = "script"            # "script", or who assessed it: "Claude", "AI"
    sources: list = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    check_by_hand: str = ""
    log: str = ""
    requirement: bool = False     # a subject sentence (shown as plain text) rather than the title of a check


@dataclass
class Buckets:
    lacking: list[Entry] = field(default_factory=list)
    second: list[Entry] = field(default_factory=list)
    ok: list[Entry] = field(default_factory=list)
    not_applicable: list[Entry] = field(default_factory=list)
    unreviewed: list[Entry] = field(default_factory=list)       # requirements nobody has assessed yet (also part of `second`)
    not_submitted: list[Entry] = field(default_factory=list)


def bucket(results: list[CheckResult], ai: AIState | None) -> Buckets:
    out = Buckets()
    seen: set[tuple] = set()
    for r in results:
        if r.status == "manual":
            review: AIReview | None = ai.reviews.get(r.rule_id) if ai and r.rule_id else None
            text = r.detail or r.title
            key = ("manual", text)
            if key in seen:
                continue
            seen.add(key)
            if review is None:
                entry = Entry(text, "not reviewed yet: a human has to judge this", sources=r.sources, requirement=True)
                out.second.append(entry)
                out.unreviewed.append(entry)
                continue
            entry = Entry(text, review.finding, by=review.by, sources=r.sources, evidence=review.evidence,
                          check_by_hand=review.why_manual, requirement=True)
            {"likely_problem": out.lacking, "unclear": out.second, "likely_ok": out.ok, "not_applicable": out.not_applicable}[review.assessment].append(entry)
            continue
        entry = Entry(r.title, r.detail, sources=r.sources, evidence=r.evidence, log=r.log if r.status in ("fail", "warn") else "")
        if r.status == "fail":
            out.lacking.append(entry)
        elif r.status in ("warn", "skipped"):
            (out.not_submitted if r.title.startswith("Bonus part not submitted") else out.second).append(entry)
        elif r.status == "pass":
            out.ok.append(entry)
    return out


# --------------------------------------------------------------------------- rendering pieces


def _entry_lines(e: Entry, *, compact: bool = False) -> list[str]:
    tag = "" if e.by == "script" else f" `{e.by}`"
    head = _inline(e.title)
    if compact:
        line = f"- {head}" + (f" — {_inline(e.detail)}" if e.detail else "") + (f" {_code(_where(e.evidence[0]))}" if e.evidence else "")
        return [line + tag]
    lines = [f"- **{head}**{tag}" + (f" — {_inline(e.detail)}" if e.detail else "") + _sources(e.sources)]
    if e.check_by_hand:
        lines.append(f"  - _Check by hand:_ {_inline(e.check_by_hand)}")
    lines += [f"  - {_code(_where(ev))}" + (f" — {_code(ev.snippet)}" if ev.snippet else "") for ev in e.evidence[:6]]
    if e.log:
        lines += ["", *("    " + l for l in _fenced(e.log[-1200:])), ""]
    return lines


def _fenced(text: str) -> list[str]:
    longest = max((len(run) for run in text.replace("\n", " ").split(" ") if set(run) == {"`"}), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence, text.rstrip(), fence]


def _section(title: str, entries: list[Entry], intro: str = "", *, compact: bool = False) -> list[str]:
    if not entries:
        return []
    out = [f"### {title} ({len(entries)})", ""]
    if intro:
        out += [intro, ""]
    for e in entries:
        out += _entry_lines(e, compact=compact)
    return out + [""]


def render_improvements(improvements: list[Improvement], readme: dict | None, *, by_claude: bool = False) -> list[str]:
    out = ["## Improvements", "",
           "> Suggestions for making the project better" + (", from claude's review" if by_claude else ", from heuristics")
           + ". They never change the result above.", ""]
    if readme is not None:
        if readme.get("present"):
            out.append(f"**README:** {_code(readme['name'])} found ({readme['lines']} non-empty lines).")
        else:
            out.append("**README:** ⚠ **no README found** in the repository.")
        out.append("")
    if not improvements:
        return out + ["No improvement suggestions.", ""]
    for category, heading in CATEGORY_TITLES.items():
        items = [i for i in improvements if i.category == category]
        if not items:
            continue
        out += [f"### {heading} ({len(items)})", ""]
        for i in items:
            tag = " _(AI)_" if i.source == "ai" and not by_claude else ""
            out.append(f"- **[{i.priority}] {_inline(i.title)}**{tag}" + (f" — {_inline(i.detail)}" if i.detail else ""))
            for e in i.evidence[:8]:
                out.append(f"  - {_code(_where(e))}" + (f" — {_code(e.snippet)}" if e.snippet else ""))
            if len(i.evidence) > 8:
                out.append(f"  - … and {len(i.evidence) - 8} more")
        out.append("")
    return out


def render_ai_overview(ai: AIState) -> list[str]:
    ov = ai.overview
    out = ["## What is in the repository (AI)", "", AI_NOTE.format(model=_inline(ai.model)), ""]
    if ov.purpose:
        out += [f"**Purpose:** {_inline(ov.purpose)}", ""]
    if ov.languages:
        out += [f"**Languages:** {', '.join(_inline(x) for x in ov.languages)}", ""]
    if ov.build_and_run:
        out += [f"**Build and run:** {_inline(ov.build_and_run)}", ""]
    if ov.components:
        out += ["| Path | Role |", "|---|---|"]
        out += [f"| {_code(c.path)} | {_inline(c.role)} |" for c in ov.components]
        out.append("")
    if ov.notable:
        out += ["**Notable:**", ""] + [f"- {_inline(x)}" for x in ov.notable] + [""]
    if ov.not_found:
        out += ["**Required by the subject but not found:**", ""] + [f"- {_inline(x)}" for x in ov.not_found] + [""]
    if ai.not_fully_sent:
        out += [f"_{len(ai.not_fully_sent)} file(s) were cut or left out of what the model saw: "
                f"{', '.join(_inline(f) for f in ai.not_fully_sent[:6])}{'…' if len(ai.not_fully_sent) > 6 else ''}._", ""]
    return out


def render_claude_prose(text: str) -> list[str]:
    """claude's free-form report, used only when its structured block could not be merged. It was written about untrusted
    code, so it is treated as untrusted text: markup defused, headings demoted, length capped, an open fence closed."""
    out = ["## Claude's review (from the terminal)", "",
           "> Written by claude in the terminal, advisory and unverified. It never changes the result above.", ""]
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
    return out + [""]


# --------------------------------------------------------------------------- the document


def render_markdown(*, repo: dict | None, subjects: list[str], results: list[CheckResult],
                    improvements: list[Improvement] | None = None, readme: dict | None = None,
                    ai: AIState | None = None, claude_review: str = "", claude: ClaudeReport | None = None,
                    project: str = "") -> str:
    claude = claude or ClaudeReport()
    summary = summarize(results, ai, claude)
    mandatory = bucket([r for r in results if r.section == "mandatory"], ai)
    bonus = bucket([r for r in results if r.section == "bonus"], ai)
    merged = claude.structured                                   # claude's answers are in the buckets; its prose is not repeated

    lacking, second = len(mandatory.lacking), len(mandatory.second)
    ok = len(mandatory.ok) + len(mandatory.not_applicable)
    icon = {"FAIL": "❌", "PASS WITH ISSUES": "⚠️"}.get(summary["overall"], "✅")
    out = [VERDICT_MARKER, "", f"# Verdict{': ' + _inline(project) if project else ''}", ""]
    if not results:
        out += ["**NOT RUN** — the checks have not been run yet.", ""]
    else:
        headline = f"{icon} **{summary['overall']}**"
        if claude.verdict:
            headline += f" · Claude: **{claude.verdict.decision}**"
        out += [headline, "",
                f"{lacking} thing(s) lacking · {second} to look at a second time · {ok} ok" + (" (mandatory part)" if bonus.ok or bonus.lacking or bonus.second else ""), ""]
    if repo:
        out.append(f"- Repository: {_inline(repo['url'])}")
        out.append(f"- Commit: {_code(repo['commit'])} {_inline(repo.get('subject', ''))} ({_inline(repo.get('author', ''))})")
    out.append("- Subjects: " + (", ".join(_inline(x) for x in subjects) or "none"))
    out.append(f"- Generated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    out.append("")
    if not results:
        return "\n".join(out).rstrip() + "\n"

    out += ["## At a glance", "", "| | ❌ Lacking | ⚠️ Second look | ✅ Ok |", "|---|---:|---:|---:|",
            f"| Mandatory part | {lacking} | {second} | {ok} |"]
    if any((bonus.lacking, bonus.second, bonus.ok, bonus.not_applicable)):
        out.append(f"| Bonus part | {len(bonus.lacking)} | {len(bonus.second)} | {len(bonus.ok) + len(bonus.not_applicable)} |")
    out += ["", "> FAIL when anything is lacking, PASS WITH ISSUES when something still needs a second look, PASS when both "
                "lists are empty. Items marked `Claude` were assessed by claude in the terminal. The peer evaluation decides the grade.", ""]

    # ---------------------------------------------------------------- lacking
    out += ["## ❌ Lacking — fix these", ""]
    if mandatory.lacking:
        for e in mandatory.lacking:
            out += _entry_lines(e)
        out.append("")
    else:
        out += ["Nothing is lacking according to the checks" + (" and claude's review." if merged else "."), ""]

    # ---------------------------------------------------------------- second look
    out += ["## ⚠️ Second look — a human should verify these", ""]
    if claude.corrections:
        out += [f"### Claude disagrees with an automated result ({len(claude.corrections)})", ""]
        for c in claude.corrections:
            out.append(f"- **{_inline(c.check)}**" + (f" — the script says: {_inline(c.says)}" if c.says else ""))
            out.append(f"  - Actually: {_inline(c.actually)}")
        out.append("")
    if mandatory.second:
        warnings = [e for e in mandatory.second if not e.requirement]
        judged = [e for e in mandatory.second if e.requirement and e not in mandatory.unreviewed]
        out += _section("Claude is unsure", judged) if merged else _section("Unclear", judged)
        out += _section("Warnings and checks that could not run", warnings)
        out += _section("Not reviewed yet — a human has to judge these", mandatory.unreviewed,
                        "Run **✨ AI review** to have claude assess them." if not merged else "", compact=True)
    elif not claude.corrections:
        out += ["Nothing needs a second look.", ""]

    # ---------------------------------------------------------------- ok
    out += ["## ✅ Ok", ""]
    checks_ok = [e for e in mandatory.ok if not e.requirement]
    reviewed_ok = [e for e in mandatory.ok if e.requirement]
    out += _section("Checks that passed", checks_ok, compact=True)
    out += _section("Requirements claude found ok", reviewed_ok, compact=True)
    out += _section("Not applicable to this project", mandatory.not_applicable, compact=True)
    if not (checks_ok or reviewed_ok or mandatory.not_applicable):
        out += ["Nothing passed yet.", ""]

    # ---------------------------------------------------------------- bonus
    if any((bonus.lacking, bonus.second, bonus.ok, bonus.not_applicable, bonus.not_submitted)):
        out += ["## Bonus part", ""]
        out += _section("Lacking", bonus.lacking) + _section("Second look", bonus.second) + _section("Ok", bonus.ok + bonus.not_applicable, compact=True)
        out += _section("Not submitted", bonus.not_submitted, compact=True)

    if ai and ai.state == "done" and ai.overview:
        out += render_ai_overview(ai)
    out += render_improvements(improvements or [], readme, by_claude=merged and bool(claude.improvements))
    if claude_review.strip() and not merged:
        if claude.problems:
            out += ["> ⚠ claude's report could not be merged into the lists above: " + " ".join(_inline(p) for p in claude.problems[:2]), ""]
        out += render_claude_prose(claude_review)
    out += render_final_verdict(summary, mandatory, claude, has_review=bool(claude_review.strip()))
    return "\n".join(out).rstrip() + "\n"


def render_final_verdict(summary: dict, mandatory: Buckets, claude: ClaudeReport, *, has_review: bool) -> list[str]:
    overall = summary["overall"]
    out = ["## Final verdict", "", f"**Result: {overall}**" + (f" · **Claude: {claude.verdict.decision}**" if claude.verdict else ""), ""]
    if claude.verdict and claude.verdict.reason:
        out += [f"> {_inline(claude.verdict.reason)}", ""]
    if overall == "NOT RUN":
        return out + ["The checks have not been run yet.", ""]

    todo = mandatory.lacking
    if todo:
        out += [f"What to do next ({len(todo)} thing(s) lacking, most important first):", ""]
        out += [f"{n}. {_inline(e.title)}" + (f" — {_inline(e.detail)}" if e.detail else "") for n, e in enumerate(todo[:8], 1)]
        if len(todo) > 8:
            out.append(f"{len(todo)}. … and {len(todo) - 8} more (listed above)")
        out.append("")
    elif overall == "PASS":
        out += ["Nothing is lacking and nothing needs a second look.", ""]
    else:
        out += ["Nothing is lacking.", ""]
    still = []
    if mandatory.second:
        still.append(f"{len(mandatory.second)} point(s) for a second look")
    if mandatory.unreviewed:
        still.append(f"{len(mandatory.unreviewed)} requirement(s) nobody has assessed yet")
    if still:
        out += ["Still open: " + "; ".join(still) + ".", ""]
    if claude.problems and claude.structured:
        out += ["_Notes on claude's report: " + " ".join(_inline(p) for p in claude.problems[:3]) + "_", ""]
    if claude.structured:
        out.append(f"Claude answered {claude.assessed} of {claude.total} requirement(s).")
    elif has_review:
        out.append("Claude's report is included above as text (it could not be merged into the lists).")
    else:
        out.append("Claude has not reviewed what the scripts could not check (use ⌨ Claude or ✨ AI review, then save).")
    out += ["", "_These results come from scripts and claude's advisory review; the peer evaluation decides the grade._"]
    return out + [""]
