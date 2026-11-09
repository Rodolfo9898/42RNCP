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

ORDER = ("fail", "warn", "manual", "skipped", "na", "pass")
AI_NOTE = ("> Written by an AI model ({model}) from a bounded view of the repository. It is advisory and unverified: "
           "it never changes the result, and file/line citations are checked against what the model was shown.")
CATEGORY_TITLES = {"structure": "Structure", "code": "Code", "logic": "Logic", "readability": "Readability"}


# Where a requirement that claude (or the AI) has judged is counted: the same place verdict.md lists it.
REVIEWED_STATUS = {"likely_problem": "fail", "unclear": "manual", "likely_ok": "pass", "not_applicable": "pass"}
# What a result becomes once claude has overwritten it.
CORRECTED_STATUS = {"likely_problem": "fail", "unclear": "warn", "likely_ok": "pass", "not_applicable": "na"}


def _key(text: str) -> str:
    return " ".join(text.replace("`", "").split()).casefold()


def _names(check: str, name: str) -> bool:
    """Does what claude wrote name this result? The prompts print `title: detail` or `title — detail`, and may cut long titles."""
    wanted, known = _key(check), _key(name)
    if not wanted or not known:
        return False
    if wanted == known or wanted.startswith((known + ":", known + " —")):
        return True
    return wanted.endswith("…") and known.startswith(wanted[:-1])


def _named(check: str, r: CheckResult) -> bool:
    return _names(check, r.title) or (r.status == "manual" and _names(check, r.detail))


def corrected(results: list[CheckResult], claude: ClaudeReport | None) -> list[CheckResult]:
    """The results as the whole evaluation reads them: what claude found different replaces the script's statement, and a
    finding about nothing known is added. `results` itself keeps what the scripts said."""
    if claude is None or not claude.corrections:
        return results
    out = list(results)
    for c in claude.corrections:
        matches = [i for i, r in enumerate(out) if r.by == "script" and _named(c.check, r)]
        replacement = {"status": CORRECTED_STATUS[c.status], "detail": c.actually, "evidence": c.evidence, "log": "", "by": "Claude", "auto": True}
        for i in matches:
            r = out[i]
            title = " ".join((r.detail or r.title).split()) if r.status == "manual" else r.title
            out[i] = r.model_copy(update={**replacement, "title": title})
        if not matches:
            out.append(CheckResult(rule_id=None, title=c.check or "Claude's finding", section=c.section, **replacement))
    return _without_repeats(out)


def _without_repeats(results: list[CheckResult]) -> list[CheckResult]:
    """The same sentence from two subjects is one requirement, so once overwritten it is listed once."""
    seen: set[str] = set()
    out = []
    for r in results:
        key = _key(r.title)
        if r.by != "script" and key in seen:
            continue
        if r.by != "script":
            seen.add(key)
        out.append(r)
    return out


def shown_status(r: CheckResult, ai: AIState | None) -> str:
    review = ai.reviews.get(r.rule_id) if ai and r.status == "manual" and r.rule_id else None
    return REVIEWED_STATUS.get(review.assessment, "manual") if review else r.status


# claude's decision, as the result it stands for. Once its report is merged, claude has the final say.
CLAUDE_DECIDES = {"ready to pass": "PASS", "pass with reservations": "PASS WITH ISSUES", "do not pass": "FAIL"}


def summarize(results: list[CheckResult], ai: AIState | None = None, claude: ClaudeReport | None = None) -> dict:
    """Before claude's review is merged the result follows the two lists of verdict.md (mandatory part): anything under
    "Lacking" is a FAIL; otherwise anything under "Second look" is a PASS WITH ISSUES; otherwise PASS. After the merge claude
    has the final say: its decision (ready to pass / pass with reservations / do not pass) is the result, and `lists` keeps
    what the lists alone would have said. The counts and the lists read what claude found, not what it overwrote."""
    shown = corrected(results, claude)
    counts = {sec: Counter(shown_status(r, ai) for r in shown if r.section == sec) for sec in ("mandatory", "bonus")}
    if not results:
        lists = "NOT RUN"
    else:
        mandatory = bucket([r for r in shown if r.section == "mandatory"], ai)
        if mandatory.lacking:
            lists = "FAIL"
        elif mandatory.second:
            lists = "PASS WITH ISSUES"
        else:
            lists = "PASS"
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
        entry = Entry(r.title, r.detail, by=r.by, sources=r.sources, evidence=r.evidence, log=r.log if r.status in ("fail", "warn") else "")
        if r.status == "fail":
            out.lacking.append(entry)
        elif r.status in ("warn", "skipped"):
            (out.not_submitted if r.title.startswith("Bonus part not submitted") else out.second).append(entry)
        elif r.status == "pass":
            out.ok.append(entry)
        elif r.status == "na":
            out.not_applicable.append(entry)
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
            out.append(f"- **[{i.priority}] {_inline(i.title)}**{tag}" + (" 🆕" if i.new else "") + (f" — {_inline(i.detail)}" if i.detail else ""))
            for e in i.evidence[:8]:
                out.append(f"  - {_code(_where(e))}" + (f" — {_code(e.snippet)}" if e.snippet else ""))
            if len(i.evidence) > 8:
                out.append(f"  - … and {len(i.evidence) - 8} more")
        out.append("")
    return out


FIX_ICONS = {"fixed": "✅", "not fixed": "❌", "not a real problem": "➖"}


def render_fixes(claude: ClaudeReport) -> list[str]:
    """What claude corrected after the review, and whether doing so turned up anything new to improve."""
    out = [f"## 🛠 What Claude corrected ({len(claude.fixes)})", ""]
    for f in claude.fixes:
        out.append(f"- {FIX_ICONS[f.status]} **{_inline(f.issue)}** — {f.status}" + (f": {_inline(f.detail)}" if f.detail else ""))
        out += [f"  - {_code(_where(e))}" for e in f.evidence[:6]]
    out.append("")
    new = [i for i in claude.improvements if i.new]
    if new:
        out += [f"**New improvements found ({len(new)}):** " + "; ".join(_inline(i.title) for i in new) + " (🆕 under Improvements).", ""]
    else:
        out += ["**New improvements found:** none.", ""]
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
    shown = corrected(results, claude)
    mandatory = bucket([r for r in shown if r.section == "mandatory"], ai)
    bonus = bucket([r for r in shown if r.section == "bonus"], ai)
    merged = claude.structured                                   # claude's answers are in the buckets; its prose is not repeated

    lacking, second = len(mandatory.lacking), len(mandatory.second)
    ok = len(mandatory.ok) + len(mandatory.not_applicable)
    icon = {"FAIL": "❌", "PASS WITH ISSUES": "⚠️"}.get(summary["overall"], "✅")
    out = [VERDICT_MARKER, "", f"# Verdict{': ' + _inline(project) if project else ''}", ""]
    if not results:
        out += ["**NOT RUN** — the checks have not been run yet.", ""]
    else:
        headline = f"{icon} **{summary['overall']}**"
        if summary["decided_by"] == "claude":
            headline += f" · decided by Claude: **{claude.verdict.decision}**"
            if summary["lists"] != summary["overall"]:
                headline += f" (the lists below alone say {summary['lists']})"
        out += [headline, ""]
        if summary["reason"]:
            out += [f"> {_inline(summary['reason'])}", ""]
        out += [f"{lacking} thing(s) lacking · {second} to look at a second time · {ok} ok" + (" (mandatory part)" if bonus.ok or bonus.lacking or bonus.second else ""), ""]
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
                "lists are empty. Once claude's review is merged, claude has the final say: ready to pass is PASS, pass with "
                "reservations is PASS WITH ISSUES, do not pass is FAIL; and what it found replaces what the scripts reported. "
                "Items marked `Claude` were assessed by claude in the terminal. The peer evaluation decides the grade.", ""]

    if claude.fixes:
        out += render_fixes(claude)

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
    if mandatory.second:
        warnings = [e for e in mandatory.second if not e.requirement and e.by == "script"]
        judged = [e for e in mandatory.second if (e.requirement or e.by != "script") and e not in mandatory.unreviewed]
        out += _section("Claude is unsure", judged) if merged else _section("Unclear", judged)
        out += _section("Warnings and checks that could not run", warnings)
        out += _section("Not reviewed yet — a human has to judge these", mandatory.unreviewed,
                        "Run **✨ AI review** to have claude assess them." if not merged else "", compact=True)
    else:
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
    decided = summary["decided_by"] == "claude"
    out = ["## Final verdict", "", f"**Result: {overall}**" + (f" · **Claude: {claude.verdict.decision}**" if decided else ""), ""]
    if decided:
        out += ["Claude has the final say" + ("" if summary["lists"] == overall else f": the lists above alone would say {summary['lists']}") + ".", ""]
    if summary["reason"]:
        out += [f"> {_inline(summary['reason'])}", ""]
    if overall == "NOT RUN":
        return out + ["The checks have not been run yet.", ""]

    todo = mandatory.lacking
    if todo:
        out += [f"What to do next ({len(todo)} thing(s) lacking, most important first):", ""]
        out += [f"{n}. {_inline(e.title)}" + (f" — {_inline(e.detail)}" if e.detail else "") for n, e in enumerate(todo[:8], 1)]
        if len(todo) > 8:
            out.append(f"{len(todo)}. … and {len(todo) - 8} more (listed above)")
        out.append("")
    elif overall == "FAIL":
        out += ["Nothing is listed as lacking, but Claude decided this does not pass: see its reason above.", ""]
    elif summary["lists"] == "PASS":
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
        out.append("Claude has not reviewed what the scripts could not check (use AI Review in the Verdict view, then Merge claude's Review).")
    out += ["", "_These results come from scripts and claude's review; the peer evaluation decides the grade._"]
    return out + [""]
