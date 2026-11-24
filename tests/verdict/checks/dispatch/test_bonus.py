"""A bonus part nobody submitted is noted once and not evaluated."""

from tests.conftest import SUBJECT_PAGES
from tests.verdict.checks.helpers import review


BONUS_PAGES = SUBJECT_PAGES + [
    "Chapter III\nBonus part\nProgram Name\nchecker\nFiles to Submit\n*.c\nMakefile\nbonus\nDescription\nx\n"
]


def test_unsubmitted_bonus_is_skipped_not_failed(good_repo):
    results = review(good_repo, pages=BONUS_PAGES)
    bonus = [r for r in results if r.section == "bonus"]
    assert len(bonus) == 1 and bonus[0].status == "skipped" and "not submitted" in bonus[0].title


def test_submitted_bonus_is_evaluated(good_repo):
    (good_repo / "checker_bonus.c").write_text("int checker(void) { return 0; }\n")
    results = review(good_repo, pages=BONUS_PAGES)
    bonus = [r for r in results if r.section == "bonus"]
    assert any(r.status == "fail" and "bonus" in r.detail.lower() for r in bonus)  # Makefile has no bonus rule
