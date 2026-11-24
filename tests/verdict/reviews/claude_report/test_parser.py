import pytest

from verdict.reviews.claude_report import parse_report
from tests.verdict.reviews.claude_report.samples import FILES, GOOD, ITEMS, report


def test_a_good_block_is_merged_completely():
    rep, reviews = parse_report(report(GOOD), ITEMS, FILES)
    assert rep.structured and rep.problems == [] and (rep.assessed, rep.total) == (3, 3)
    assert set(reviews) == {"r1", "r1b", "r2", "r3"}                         # an item shared by two rules answers both
    r1 = reviews["r1"]
    assert (r1.assessment, r1.by, r1.finding, r1.why_manual) == ("likely_problem", "Claude", "Bytes above 0x7f are missed.", "Run on x86.")
    assert [(e.file, e.line) for e in r1.evidence] == [("ft_strchr.c", 20)]
    assert reviews["r2"].assessment == "unclear" and [(e.file, e.line) for e in reviews["r2"].evidence] == [("Makefile", 23)]
    assert reviews["r3"].assessment == "likely_ok"
    assert rep.corrections[0].actually == "ft_lst*.c exist" and rep.corrections[0].status == "likely_ok"
    assert [e.file for e in rep.corrections[0].evidence] == ["main.c"] and rep.fixes == []
    assert rep.verdict.decision == "do not pass" and rep.verdict.reason == "README missing."
    assert rep.improvements[0].title == "Fix strchr" and rep.improvements[0].source == "ai" and rep.improvements[0].priority == "high"


def test_without_a_block_nothing_is_merged_and_the_user_is_told_why():
    rep, reviews = parse_report("# only prose", ITEMS, FILES)
    assert not rep.structured and reviews == {} and rep.total == 3
    assert "no json block" in rep.problems[0] and "Ask claude to add it" in rep.problems[0]


@pytest.mark.parametrize("raw,expected", [
    ("likely ok", "likely_ok"), ("OK", "likely_ok"), ("Likely_OK", "likely_ok"), ("pass", "likely_ok"),
    ("likely a problem", "likely_problem"), ("problem", "likely_problem"), ("FAIL", "likely_problem"),
    ("unclear", "unclear"), ("unsure", "unclear"), ("not applicable", "not_applicable"), ("N/A", "not_applicable"), ("not_applicable", "not_applicable"),
])
def test_status_wording_is_forgiving(raw, expected):
    _, reviews = parse_report(report({"items": [{"n": 1, "status": raw, "note": "x"}]}), ITEMS, FILES)
    assert reviews["r1"].assessment == expected


def test_unknown_numbers_statuses_and_missing_answers_are_reported_not_hidden():
    data = {"items": [{"n": 1, "status": "maybe?", "note": "x"}, {"n": 99, "status": "ok"}, {"n": "two", "status": "ok"}, {"status": "ok"}, "junk"]}
    rep, reviews = parse_report(report(data), ITEMS, FILES)
    assert reviews["r1"].assessment == "unclear"                              # an unknown status never becomes "ok"
    assert set(reviews) == {"r1", "r1b"}
    text = " ".join(rep.problems)
    assert "unknown status" in text and "Item 99 does not exist" in text and "without a usable number" in text
    assert "did not answer 2 of 3 requirement(s): #2, #3" in text and (rep.assessed, rep.total) == (1, 3)


def test_a_requirement_claude_skipped_has_no_review():
    _, reviews = parse_report(report({"items": [{"n": 1, "status": "ok"}]}), ITEMS, FILES)
    assert "r2" not in reviews and "r3" not in reviews


def test_control_characters_are_removed_and_long_text_is_capped():
    data = {"items": [{"n": 1, "status": "ok", "note": "a\x00b\x1bc" + "x" * 5000}]}
    _, reviews = parse_report(report(data), ITEMS, FILES)
    note = reviews["r1"].finding
    assert "\x00" not in note and "\x1b" not in note and note.startswith("abc") and len(note) <= 700 and note.endswith("…")
