from verdict.core.models import AIReview, AIState, CheckResult, Source
from verdict.reports.report import Bucketer, bucket


def result(status, title="T", detail="", **kw):
    return CheckResult(rule_id=kw.pop("rule_id", None), title=title, status=status, detail=detail, **kw)


def titles(entries):
    return [e.title for e in entries]


def test_a_check_goes_where_its_status_says():
    out = bucket([result("fail", "a"), result("warn", "b"), result("skipped", "c"), result("pass", "d"), result("na", "e")], None)
    assert titles(out.lacking) == ["a"] and titles(out.second) == ["b", "c"] and titles(out.ok) == ["d"] and titles(out.not_applicable) == ["e"]


def test_a_bonus_that_was_not_submitted_is_listed_apart_from_the_second_look():
    out = bucket([result("skipped", "Bonus part not submitted", section="bonus"), result("warn", "b", section="bonus")], None)
    assert titles(out.not_submitted) == ["Bonus part not submitted"] and titles(out.second) == ["b"]


def test_the_log_of_a_check_is_kept_only_when_it_failed_or_warned():
    out = bucket([result("fail", "a", log="boom"), result("warn", "b", log="hmm"), result("pass", "c", log="fine")], None)
    assert [e.log for e in out.lacking + out.second + out.ok] == ["boom", "hmm", ""]


def test_a_requirement_nobody_judged_waits_for_a_human_and_is_counted_as_unreviewed():
    out = bucket([result("manual", "Needs manual review", "Handles bad input.", rule_id="r1", sources=[Source(pdf="p.pdf", page=2)])], None)
    assert titles(out.second) == titles(out.unreviewed) == ["Handles bad input."]
    assert out.second[0].requirement and out.second[0].detail == "not reviewed yet: a human has to judge this" and out.second[0].sources[0].page == 2


def test_a_requirement_goes_where_its_assessment_says_and_carries_who_said_it():
    ai = AIState(reviews={f"r{i}": AIReview(rule_id=f"r{i}", assessment=a, by="Claude", finding=f"f{i}", why_manual="look")
                          for i, a in enumerate(["likely_problem", "unclear", "likely_ok", "not_applicable"])})
    results = [result("manual", "Needs manual review", f"Requirement {i}.", rule_id=f"r{i}") for i in range(4)]
    out = Bucketer(ai).sort(results)
    assert titles(out.lacking) == ["Requirement 0."] and titles(out.second) == ["Requirement 1."]
    assert titles(out.ok) == ["Requirement 2."] and titles(out.not_applicable) == ["Requirement 3."] and out.unreviewed == []
    assert out.lacking[0].by == "Claude" and out.lacking[0].detail == "f0" and out.lacking[0].check_by_hand == "look"


def test_the_same_sentence_from_two_subjects_is_one_requirement():
    results = [result("manual", "Needs manual review", "Same sentence.", rule_id="r1"), result("manual", "Needs manual review", "Same sentence.", rule_id="r2")]
    assert titles(bucket(results, None).second) == ["Same sentence."]
