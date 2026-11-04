"""Read the structured block at the end of claude's report and turn it into assessments for the verdict.

claude writes a free-form report (kept as claude-review.md) and ends it with one fenced json block. Only that block is
merged into verdict.md, so the document stays one readable page instead of two. Everything in it is checked: unknown
requirement numbers are ignored, and a cited file or line that does not exist is dropped rather than shown.

A block with a "fixes" key is an update, written after claude fixed something: it is laid over the previous report, so it only
has to say what changed.
"""

from __future__ import annotations

import json
import re

from .models import AIReview, ClaudeReport, ClaudeVerdict, Correction, Evidence, Fix, Improvement, ReviewItem

STATUS = {
    "likely ok": "likely_ok", "likely_ok": "likely_ok", "ok": "likely_ok", "pass": "likely_ok", "passes": "likely_ok",
    "likely a problem": "likely_problem", "likely problem": "likely_problem", "likely_problem": "likely_problem",
    "problem": "likely_problem", "fail": "likely_problem", "fails": "likely_problem", "not ok": "likely_problem",
    "unclear": "unclear", "unsure": "unclear", "unknown": "unclear", "partial": "unclear",
    "not applicable": "not_applicable", "not_applicable": "not_applicable", "n/a": "not_applicable", "na": "not_applicable",
}
DECISION = {
    "ready to pass": "ready to pass", "pass": "ready to pass", "passes": "ready to pass",
    "pass with reservations": "pass with reservations", "pass with reservation": "pass with reservations",
    "reservations": "pass with reservations", "do not pass": "do not pass", "fail": "do not pass", "dont pass": "do not pass",
}
FIX_STATUS = {
    "fixed": "fixed", "done": "fixed", "not fixed": "not fixed", "unfixed": "not fixed", "not a real problem": "not a real problem",
    "not real": "not a real problem", "not a problem": "not a real problem",
}
CATEGORIES = {"structure", "code", "logic", "readability"}
PRIORITIES = {"high", "medium", "low"}


def fenced_blocks(markdown: str) -> list[tuple[str, str]]:
    """(language, body) of every fenced code block, reading line by line so that a closing fence is never mistaken
    for the opening of the next block (claude's prose usually has other code blocks before the json)."""
    blocks: list[tuple[str, str]] = []
    opener = ""            # the fence characters that opened the current block ("" outside one)
    language, body = "", []
    for line in markdown.splitlines():
        stripped = line.strip()
        marker = re.match(r"(`{3,}|~{3,})(.*)$", stripped)
        if not opener:
            if marker:
                opener, language, body = marker.group(1), marker.group(2).strip().lower(), []
        elif marker and marker.group(1)[0] == opener[0] and len(marker.group(1)) >= len(opener) and not marker.group(2).strip():
            blocks.append((language, "\n".join(body)))
            opener = ""
        else:
            body.append(line)
    return blocks                      # an unclosed block at the end is not data


def extract_block(markdown: str) -> dict | None:
    """The last json block that looks like the report data."""
    for language, body in reversed(fenced_blocks(markdown)):
        if language not in ("", "json", "jsonc"):
            continue
        try:
            data = json.loads(body)
        except ValueError:
            continue
        if isinstance(data, dict) and ("items" in data or "verdict" in data or "fixes" in data):
            return data
    return None


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", " "))


def citations(raw: object, files: dict[str, int]) -> list[Evidence]:
    """'file:line', 'file:12-20' or 'file:7,9' -> Evidence, keeping only files and lines that exist."""
    out: list[Evidence] = []
    for entry in raw if isinstance(raw, list) else []:
        match = re.match(r"^\s*(?:\./)?(.+?)(?::(\d+))?(?:[-,–]\d+)*\s*$", str(entry))
        if not match:
            continue
        file, line = match.group(1), int(match.group(2)) if match.group(2) else None
        total = files.get(file)
        if total is None or (line is not None and not 1 <= line <= total):
            continue
        out.append(Evidence(file=file, line=line))
        if len(out) >= 5:
            break
    return out


def _text(value: object, limit: int) -> str:
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _corrections(raw: object, files: dict[str, int], problems: list[str]) -> list[Correction]:
    out: list[Correction] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict) or not entry.get("actually"):
            continue
        check = _text(entry.get("check"), 240)
        status = STATUS.get(_norm(entry.get("status")))
        if status is None:
            problems.append(f"The correction of {check!r} has no usable status; it is listed under 'second look'.")
        out.append(Correction(check=check, says=_text(entry.get("says"), 300), actually=_text(entry.get("actually"), 500),
                              status=status or "unclear", evidence=citations(entry.get("evidence"), files),
                              section="bonus" if _norm(entry.get("section")) == "bonus" else "mandatory"))
    return out


def _fixes(raw: object, files: dict[str, int]) -> list[Fix]:
    return [Fix(issue=_text(entry.get("issue"), 240), status=FIX_STATUS.get(_norm(entry.get("status")), "fixed"),
                detail=_text(entry.get("detail"), 600), evidence=citations(entry.get("evidence"), files))
            for entry in (raw if isinstance(raw, list) else []) if isinstance(entry, dict) and entry.get("issue")]


def parse_report(markdown: str, items: list[ReviewItem], files: dict[str, int], previous: ClaudeReport | None = None,
                 previous_reviews: dict[str, AIReview] | None = None) -> tuple[ClaudeReport, dict[str, AIReview]]:
    """Returns (report, reviews by rule id). `report.structured` is False when nothing usable was found. An update (a block with
    "fixes") is laid over `previous`: what it says replaces what was there, and what it leaves out stays."""
    data = extract_block(markdown)
    if data is None:
        return ClaudeReport(total=len(items), problems=["The report has no json block at the end, so it could not be merged. "
                                                        "Ask claude to add it (the shape is in the prompt)."]), {}
    problems: list[str] = []
    reviews: dict[str, AIReview] = {}
    by_number = {item.n: item for item in items}
    answered: set[int] = set()
    for entry in data.get("items") or []:
        if not isinstance(entry, dict):
            continue
        try:
            number = int(entry.get("n"))
        except (TypeError, ValueError):
            problems.append(f"An item without a usable number was ignored: {_text(entry, 60)!r}.")
            continue
        item = by_number.get(number)
        status = STATUS.get(_norm(entry.get("status")))
        if item is None:
            problems.append(f"Item {number} does not exist in the prompt and was ignored.")
            continue
        if status is None:
            problems.append(f"Item {number} has an unknown status {_text(entry.get('status'), 30)!r}; treated as unclear.")
            status = "unclear"
        answered.add(number)
        for rule_id in item.rule_ids:
            reviews[rule_id] = AIReview(
                rule_id=rule_id, assessment=status, finding=_text(entry.get("note"), 700),
                why_manual=_text(entry.get("check_by_hand"), 400), evidence=citations(entry.get("evidence"), files), by="Claude")
    is_fix_report = "fixes" in data
    layered = is_fix_report and previous is not None and previous.structured
    if layered:
        reviews = {**(previous_reviews or {}), **reviews}
        answered |= {item.n for item in items if any(rule_id in reviews for rule_id in item.rule_ids)}
    missing = sorted(set(by_number) - answered)
    if missing:
        problems.append(f"Claude did not answer {len(missing)} of {len(by_number)} requirement(s): "
                        f"{', '.join('#' + str(n) for n in missing[:12])}{'…' if len(missing) > 12 else ''}. They stay under 'second look'.")

    corrections = _corrections(data.get("corrections"), files, problems)
    fixes = _fixes(data.get("fixes"), files)
    improvements = []
    for entry in data.get("improvements") or []:
        if not isinstance(entry, dict) or not entry.get("title"):
            continue
        category, priority = _norm(entry.get("category")), _norm(entry.get("priority"))
        improvements.append(Improvement(
            category=category if category in CATEGORIES else "code", priority=priority if priority in PRIORITIES else "medium",
            title=_text(entry.get("title"), 140), detail=_text(entry.get("detail"), 600),
            evidence=citations(entry.get("evidence"), files), source="ai"))
    verdict = None
    raw_verdict = data.get("verdict")
    if isinstance(raw_verdict, dict) and DECISION.get(_norm(raw_verdict.get("decision"))):
        verdict = ClaudeVerdict(decision=DECISION[_norm(raw_verdict["decision"])], reason=_text(raw_verdict.get("reason"), 600))
    elif raw_verdict:
        problems.append("The verdict in the block was not one of: ready to pass, pass with reservations, do not pass.")
    known = {_norm(i.title) for i in previous.improvements} if layered else set()
    if is_fix_report:
        for improvement in improvements:
            improvement.new = _norm(improvement.title) not in known
    if layered:
        corrections = list({_norm(c.check): c for c in [*previous.corrections, *corrections]}.values())   # the latest word on each
        fixes = list({_norm(f.issue): f for f in [*previous.fixes, *fixes]}.values())
        verdict = verdict or previous.verdict
        if "improvements" not in data:
            improvements = [i.model_copy(update={"new": False}) for i in previous.improvements]
    report = ClaudeReport(structured=True, corrections=corrections, fixes=fixes, verdict=verdict, improvements=improvements,
                          assessed=len(answered), total=len(by_number), problems=problems)
    return report, reviews
