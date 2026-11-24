import pytest

from verdict.reviews.claude_report import parse_report
from tests.verdict.reviews.claude_report.samples import FILES, ITEMS, report


def test_improvements_are_cleaned_up():
    data = {"items": [], "improvements": [
        {"category": "weird", "priority": "urgent", "title": "T1", "detail": "d", "evidence": ["ghost.c:1"]},
        {"category": "Logic", "priority": "LOW", "title": "T2"},
        {"title": ""}, {"detail": "no title"}, "junk"]}
    rep, _ = parse_report(report(data), ITEMS, FILES)
    assert [(i.title, i.category, i.priority, i.evidence) for i in rep.improvements] == [("T1", "code", "medium", []), ("T2", "logic", "low", [])]


@pytest.mark.parametrize("raw,decision", [("ready to pass", "ready to pass"), ("PASS", "ready to pass"), ("pass with reservations", "pass with reservations"),
                                          ("do not pass", "do not pass"), ("fail", "do not pass")])
def test_verdict_wording(raw, decision):
    rep, _ = parse_report(report({"items": [], "verdict": {"decision": raw, "reason": "because"}}), ITEMS, FILES)
    assert rep.verdict.decision == decision


def test_an_unusable_verdict_is_reported():
    rep, _ = parse_report(report({"items": [], "verdict": {"decision": "looks great!", "reason": "x"}}), ITEMS, FILES)
    assert rep.verdict is None and any("not one of" in p for p in rep.problems)


def test_corrections_need_to_say_what_is_actually_true():
    data = {"items": [], "corrections": [{"check": "A", "says": "x", "actually": "y"}, {"check": "B", "says": "x"}, "junk"]}
    rep, _ = parse_report(report(data), ITEMS, FILES)
    assert [c.check for c in rep.corrections] == ["A"]
