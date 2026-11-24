from verdict.core.models import CheckResult
from verdict.reviews.ai import analysis_task, review_task
from verdict.reviews.prompts import build_fix_prompt, build_review_prompt
from tests.verdict.reviews.prompts.samples import REPORT_DIR, build, fix, r


def test_the_review_and_the_fix_prompt_both_say_to_test_in_the_current_directory_never_in_tmp():
    from shared.constants import TEST_HERE
    assert "never copy the project to /tmp" in TEST_HERE and "current directory" in TEST_HERE
    review, _ = build()
    assert TEST_HERE in review.split("HOW TO WORK")[1]
    fix_prompt, _ = fix([r("fail", "Passes norminette", "2 errors")])
    assert TEST_HERE in fix_prompt.split("HOW TO WORK")[1]
    cpp, _ = build_fix_prompt(report_dir=REPORT_DIR, project="cpp01", subjects=[], lang="cpp", results=[r("fail", "Compiles", "No.")])
    assert TEST_HERE in cpp


def test_every_prompt_says_the_evaluators_requests_are_carried_out_and_settled_points_are_not_applicable():
    from terminal.claude import prompts as terminal
    for text in (build()[0], fix([r("fail", "Required files", "Missing: a.c")])[0], terminal.APPEND_PROMPT, terminal.APPEND_PROMPT_LIVE):
        assert "is the only one" in text and "do exactly what was asked" in text
        assert "that request wins" in text and "say in one line what blocked you" in text
        assert '"not applicable"' in text and "already settled" in text
    for text in (terminal.APPEND_PROMPT, terminal.APPEND_PROMPT_LIVE):
        assert "Never add a library, a dependency or an external function" in text
        assert 'Always include the "fixes" key' in text


def test_the_prompts_tell_claude_to_just_run_the_evaluation_files():
    review, _ = build_review_prompt(report_dir=REPORT_DIR, project="philo", subjects=["philosophers.pdf"], lang="c", results=[])
    assert "never a finding" in review and "do not mention them" in review and "directly" in review


# ---------------------------------------------------------------- the prompts say the same


def test_every_prompt_carries_the_evaluators_rules():
    review, _ = build_review_prompt(report_dir=REPORT_DIR, project="philo", subjects=["philosophers.pdf"], lang="c", results=[])
    assert "HOW I READ THE SUBJECT" in review and "DRY" in review and "submodule" in review and "MiniLibX" in review
    strict, _ = build_review_prompt(report_dir=REPORT_DIR, project="libft", subjects=["libft.pdf"], lang="c", results=[])
    assert "respect the subject's format exactly" in strict
    failed = CheckResult(rule_id="x", title="Required files", status="fail", detail="Missing: philo_bonus/")
    fix, stats = build_fix_prompt(report_dir=REPORT_DIR, project="philo", subjects=["philosophers.pdf"], lang="c", results=[failed])
    assert stats["issues"] and "HOW THE EVALUATOR READS THE SUBJECT" in fix and "do not duplicate shared code" in fix
    assert "DRY" in review_task([("r1", "x")], ["philosophers.pdf"]) and "DRY" in analysis_task(["philosophers.pdf"], "s", [])
