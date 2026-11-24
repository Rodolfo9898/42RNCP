"""The words claude may use for a status, a decision, a category, and how its text is normalised."""

from __future__ import annotations

import re

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


def norm(value: object) -> str:
    """Lower case, one space between words, underscores as spaces: the form the vocabularies are keyed by."""
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", " "))


def text(value: object, limit: int) -> str:
    """Control characters removed, cut to `limit` characters."""
    cleaned = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(value or "")).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"
