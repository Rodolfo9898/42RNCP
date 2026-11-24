import pytest

from verdict.core.models import ClaudeReport, ClaudeVerdict, Correction
from verdict.reports.report import summarize
from tests.verdict.reports.report.helpers import decided, fix_of, judged, manual, report_with, result


def test_verdict_levels():
    assert summarize([])["overall"] == "NOT RUN"
    assert summarize([result("pass")])["overall"] == "PASS"
    assert summarize([result("pass"), result("manual")])["overall"] == "PASS WITH ISSUES"
    assert summarize([result("pass"), result("fail")])["overall"] == "FAIL"
    assert summarize([result("pass"), result("fail"), result("manual"), result("warn")])["overall"] == "FAIL"   # lacking wins
    assert summarize([result("pass"), result("fail", section="bonus")])["overall"] == "PASS"


def test_the_result_follows_the_two_lists_including_claudes_answers():
    results = [result("pass"), manual("r1", "Handles bad input."), manual("r2", "Never crashes.")]
    # both lists empty: claude found every requirement ok (or not applicable)
    assert summarize(results, judged(r1="likely_ok", r2="not_applicable"), ClaudeReport())["overall"] == "PASS"
    # only something for a second look
    assert summarize(results, judged(r1="likely_ok", r2="unclear"), ClaudeReport())["overall"] == "PASS WITH ISSUES"
    assert summarize(results, judged(r1="likely_ok"), ClaudeReport())["overall"] == "PASS WITH ISSUES"            # r2 not reviewed
    disagrees = ClaudeReport(corrections=[Correction(check="T", says="ok", actually="it is not")])
    assert summarize(results, judged(r1="likely_ok", r2="likely_ok"), disagrees)["overall"] == "PASS WITH ISSUES"
    # anything lacking is a fail, whatever else there is
    assert summarize(results, judged(r1="likely_problem", r2="likely_ok"), ClaudeReport())["overall"] == "FAIL"
    assert summarize(results, judged(r1="likely_problem", r2="unclear"), disagrees)["overall"] == "FAIL"


def test_claudes_decision_is_the_result_whatever_the_lists_say():
    failing = [result("pass"), result("fail")]
    clean = [result("pass")]
    for decision, expected in (("ready to pass", "PASS"), ("pass with reservations", "PASS WITH ISSUES"), ("do not pass", "FAIL")):
        for results, lists in ((failing, "FAIL"), (clean, "PASS")):
            summary, _ = decided(decision, results)
            assert (summary["overall"], summary["decided_by"], summary["lists"]) == (expected, "claude", lists), (decision, lists)


def test_without_a_decision_from_claude_the_lists_decide_as_before():
    results = [result("pass"), result("fail")]
    for claude in (None, ClaudeReport(), ClaudeReport(structured=True)):                  # no review, or a report with no verdict in it
        summary = summarize(results, None, claude)
        assert (summary["overall"], summary["decided_by"], summary["lists"]) == ("FAIL", "scripts", "FAIL")
    assert summarize([], None, ClaudeReport(verdict=ClaudeVerdict(decision="ready to pass")))["overall"] == "NOT RUN"     # nothing to decide on


@pytest.mark.parametrize("decision,overall", [("ready to pass", "PASS"), ("pass with reservations", "PASS WITH ISSUES"), ("do not pass", "FAIL")])
@pytest.mark.parametrize("scripts", ["pass", "warn", "fail"])
def test_claudes_decision_and_reason_set_the_result_whatever_the_scripts_said(decision, overall, scripts):
    summary = summarize([result(scripts)], None, report_with(decision=decision))
    assert (summary["overall"], summary["decided_by"], summary["reason"]) == (overall, "claude", "Because.")


def test_the_lists_read_what_claude_found_not_what_it_overwrote():
    summary = summarize([result("fail", title="A", detail="false alarm")], None, report_with(fix_of("A"), decision="do not pass"))
    assert (summary["overall"], summary["lists"], summary["mandatory"]["fail"], summary["mandatory"]["pass"]) == ("FAIL", "PASS", 0, 1)


def test_without_a_decision_the_lists_decide():
    assert summarize([result("fail")], None, report_with()) | {"mandatory": 0, "bonus": 0} == {
        "overall": "FAIL", "decided_by": "scripts", "lists": "FAIL", "reason": "", "mandatory": 0, "bonus": 0}
