from verdict.reviews.claude_report import parse_report
from tests.verdict.reviews.claude_report.samples import FILES, GOOD, ITEMS, report


def first_report():
    return parse_report(report(GOOD), ITEMS, FILES)


def update(data, previous=None):
    rep, reviews = previous or first_report()
    return parse_report(report(data), ITEMS, FILES, previous=rep, previous_reviews=reviews)


def test_an_update_only_has_to_say_what_changed():
    rep, reviews = update({"fixes": [{"issue": "Fix strchr", "status": "fixed", "detail": "Cast to unsigned char.", "evidence": ["ft_strchr.c:20", "ghost.c:1"]}],
                           "items": [{"n": 1, "status": "likely ok", "note": "Fixed now."}]})
    assert rep.structured and rep.problems == [] and (rep.assessed, rep.total) == (3, 3)
    assert reviews["r1"].assessment == "likely_ok" and reviews["r1b"].finding == "Fixed now."
    assert reviews["r2"].assessment == "unclear" and reviews["r3"].assessment == "likely_ok"       # the rest stands
    assert rep.verdict.decision == "do not pass" and rep.corrections[0].check == "Makefile has a bonus rule"
    assert [(f.issue, f.status, [e.file for e in f.evidence]) for f in rep.fixes] == [("Fix strchr", "fixed", ["ft_strchr.c"])]


def test_an_update_replaces_the_verdict_and_the_correction_of_the_same_check():
    rep, _ = update({"fixes": [], "verdict": {"decision": "ready to pass", "reason": "All fixed."},
                     "corrections": [{"check": "MAKEFILE has a bonus rule", "status": "likely a problem", "actually": "Removed by mistake."}]})
    assert rep.verdict.decision == "ready to pass"
    assert [(c.status, c.actually) for c in rep.corrections] == [("likely_problem", "Removed by mistake.")]


def test_new_improvements_are_marked_and_the_list_is_replaced():
    rep, _ = update({"fixes": [], "improvements": [{"title": "FIX STRCHR", "category": "code"}, {"title": "Split main", "category": "structure"}]})
    assert [(i.title, i.new) for i in rep.improvements] == [("FIX STRCHR", False), ("Split main", True)]
    done, _ = update({"fixes": [], "improvements": []})
    assert done.improvements == []


def test_an_update_that_leaves_improvements_out_keeps_them_and_nothing_is_new():
    first = update({"fixes": [], "improvements": [{"title": "Split main", "category": "structure"}]})
    rep, _ = update({"fixes": []}, previous=first)
    assert [(i.title, i.new) for i in rep.improvements] == [("Split main", False)]


def test_fixes_add_up_over_several_rounds_with_the_latest_word_on_each():
    one = update({"fixes": [{"issue": "Leak", "status": "not fixed"}, {"issue": "Norm", "status": "fixed"}]})
    rep, _ = update({"fixes": [{"issue": "leak", "status": "fixed", "detail": "Freed it."}]}, previous=one)
    assert [(f.issue, f.status) for f in rep.fixes] == [("leak", "fixed"), ("Norm", "fixed")]


def test_a_new_full_report_replaces_everything():
    first = update({"fixes": [{"issue": "Leak"}]})
    rep, reviews = parse_report(report({"items": [{"n": 1, "status": "ok"}]}), ITEMS, FILES, previous=first[0], previous_reviews=first[1])
    assert rep.fixes == [] and rep.verdict is None and set(reviews) == {"r1", "r1b"} and any("did not answer" in p for p in rep.problems)


def test_fixes_without_an_earlier_report_stand_alone():
    rep, reviews = parse_report(report({"fixes": [{"issue": "Leak", "status": "weird"}], "improvements": [{"title": "A", "category": "code"}]}), ITEMS, FILES)
    assert rep.structured and rep.fixes[0].status == "fixed" and rep.improvements[0].new and reviews == {}


def test_a_correction_with_no_usable_status_is_reported():
    rep, _ = parse_report(report({"items": [], "corrections": [{"check": "A", "status": "banana", "actually": "y"}, {"check": "B", "status": "bonus", "actually": "z", "section": "bonus"}]}), ITEMS, FILES)
    assert [c.status for c in rep.corrections] == ["unclear", "unclear"] and rep.corrections[1].section == "bonus"
    assert sum("no usable status" in p for p in rep.problems) == 2


def test_a_block_without_items_is_an_update_that_keeps_the_earlier_answers():
    """Settling points with the evaluator writes only corrections and a verdict: that must not wipe the item answers."""
    from verdict.reviews.claude_report import parse_report
    from verdict.core.models import ReviewItem
    items = [ReviewItem(n=1, text="a", rule_ids=["r1"]), ReviewItem(n=2, text="b", rule_ids=["r2"])]
    full = '```json\n{"items": [{"n": 1, "status": "likely ok", "note": "fine"}, {"n": 2, "status": "unclear", "note": "?"}], "verdict": {"decision": "pass with reservations", "reason": "x"}}\n```'
    first, reviews = parse_report(full, items, {})
    update = '```json\n{"corrections": [{"check": "Needs manual review", "status": "not applicable", "actually": "settled with the evaluator"}], "verdict": {"decision": "ready to pass", "reason": "y"}}\n```'
    second, merged = parse_report(update, items, {}, previous=first, previous_reviews=reviews)
    assert set(merged) == {"r1", "r2"} and second.assessed == 2                      # earlier answers stay
    assert second.verdict.decision == "ready to pass" and second.corrections[0].status == "not_applicable"
