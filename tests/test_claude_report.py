import json

import pytest

from verdict.claude_report import citations, extract_block, parse_report
from verdict.models import ReviewItem

FILES = {"ft_strchr.c": 30, "Makefile": 60, "main.c": 10}
ITEMS = [ReviewItem(n=1, text="strchr must work", rule_ids=["r1", "r1b"]), ReviewItem(n=2, text="no relink", rule_ids=["r2"]),
         ReviewItem(n=3, text="bonus files", rule_ids=["r3"])]


def report(data, prose="# My review\n\nSome prose.\n"):
    return f"{prose}\n```json\n{json.dumps(data)}\n```\n"


GOOD = {
    "items": [
        {"n": 1, "status": "likely a problem", "note": "Bytes above 0x7f are missed.", "check_by_hand": "Run on x86.", "evidence": ["ft_strchr.c:20,24"]},
        {"n": 2, "status": "unclear", "note": "bonus relinks.", "check_by_hand": "", "evidence": ["Makefile:23-25"]},
        {"n": 3, "status": "likely ok", "note": "Fine.", "evidence": []},
    ],
    "corrections": [{"check": "Makefile has a bonus rule", "says": "no bonus files", "actually": "ft_lst*.c exist"}],
    "improvements": [{"category": "code", "priority": "high", "title": "Fix strchr", "detail": "cast", "evidence": ["ft_strchr.c:20"]}],
    "verdict": {"decision": "do not pass", "reason": "README missing."},
}


def test_a_good_block_is_merged_completely():
    rep, reviews = parse_report(report(GOOD), ITEMS, FILES)
    assert rep.structured and rep.problems == [] and (rep.assessed, rep.total) == (3, 3)
    assert set(reviews) == {"r1", "r1b", "r2", "r3"}                         # an item shared by two rules answers both
    r1 = reviews["r1"]
    assert (r1.assessment, r1.by, r1.finding, r1.why_manual) == ("likely_problem", "Claude", "Bytes above 0x7f are missed.", "Run on x86.")
    assert [(e.file, e.line) for e in r1.evidence] == [("ft_strchr.c", 20)]
    assert reviews["r2"].assessment == "unclear" and [(e.file, e.line) for e in reviews["r2"].evidence] == [("Makefile", 23)]
    assert reviews["r3"].assessment == "likely_ok"
    assert rep.corrections[0].actually == "ft_lst*.c exist"
    assert rep.verdict.decision == "do not pass" and rep.verdict.reason == "README missing."
    assert rep.improvements[0].title == "Fix strchr" and rep.improvements[0].source == "ai" and rep.improvements[0].priority == "high"


def test_only_the_last_valid_json_block_counts():
    other = '```json\n{"unrelated": true}\n```\n```python\nprint(1)\n```\n'
    broken = '```json\n{not json}\n```\n'
    text = report({"items": [{"n": 1, "status": "ok"}]}, prose="first") + other + report(GOOD, prose="second") + broken
    assert extract_block(text) == GOOD
    assert extract_block("no fences here") is None and extract_block('```json\n{"x": 1}\n```') is None


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


@pytest.mark.parametrize("cited,expected", [
    (["ft_strchr.c:20"], [("ft_strchr.c", 20)]),
    (["ft_strchr.c:20,24", "Makefile:23-25"], [("ft_strchr.c", 20), ("Makefile", 23)]),
    (["./main.c:3"], [("main.c", 3)]),
    (["Makefile"], [("Makefile", None)]),
    (["ghost.c:1", "ft_strchr.c:31", "ft_strchr.c:0", "../etc/passwd:1", "/etc/passwd"], []),
    (["main.c:1", "main.c:2", "main.c:3", "main.c:4", "main.c:5", "main.c:6"], [("main.c", n) for n in range(1, 6)]),
    ("not a list", []), ([None, 5, {}], []),
])
def test_citations_must_point_at_real_files_and_lines(cited, expected):
    assert [(e.file, e.line) for e in citations(cited, FILES)] == expected


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


def test_control_characters_are_removed_and_long_text_is_capped():
    data = {"items": [{"n": 1, "status": "ok", "note": "a\x00b\x1bc" + "x" * 5000}]}
    _, reviews = parse_report(report(data), ITEMS, FILES)
    note = reviews["r1"].finding
    assert "\x00" not in note and "\x1b" not in note and note.startswith("abc") and len(note) <= 700 and note.endswith("…")


def test_other_code_blocks_in_the_prose_do_not_confuse_the_reader():
    prose = ("# Review\n\nThe bug:\n\n```c\nint f(void)\n{\n\treturn (0);\n}\n```\n\nAnd a shell session:\n\n```sh\nmake re\n```\n\n"
             "~~~\nplain tilde block with ``` inside\n~~~\n\n## Verdict\ndo not pass\n")
    data = extract_block(report(GOOD, prose=prose))
    assert data == GOOD


def test_a_json_example_inside_the_prose_is_not_mistaken_for_the_data():
    prose = 'I will end the file with:\n\n```json\n{"items": [{"n": 1, "status": "ok"}]}\n```\n'
    assert extract_block(report(GOOD, prose=prose)) == GOOD                      # the last block wins
    assert extract_block(prose) == {"items": [{"n": 1, "status": "ok"}]}


def test_an_unclosed_block_is_not_data():
    assert extract_block('```json\n{"items": []}\n') is None


def test_the_block_may_have_no_language_tag_but_other_languages_are_skipped():
    assert extract_block('```\n{"items": []}\n```') == {"items": []}
    assert extract_block('```yaml\n{"items": []}\n```') is None
