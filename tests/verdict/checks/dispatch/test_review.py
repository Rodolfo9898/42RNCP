"""The whole review: run_checks over a subject's rules and a repository."""

import shutil

import pytest

from verdict.checks import Ctx, run_checks
from verdict.core.models import CheckResult
from verdict.subjects.spec import parse_subject

from tests.conftest import SUBJECT_PAGES
from tests.verdict.checks.helpers import by_title, project, review


def test_static_checks_on_good_repo(good_repo):
    results = review(good_repo)
    assert by_title(results, "Required files").status == "pass"
    assert by_title(results, "Makefile rules").status == "pass"
    assert by_title(results, "Written in C").status == "pass"
    assert by_title(results, "build artifacts").status == "pass"
    assert by_title(results, "secrets").status == "pass"


def test_without_sandbox_dynamic_checks_are_skipped_not_failed(good_repo):
    results = review(good_repo)
    build = by_title(results, "Builds")
    assert build.status == "skipped"
    assert not any(r.status == "fail" for r in results)


def test_static_checks_on_bad_repo(bad_repo):
    results = review(bad_repo)
    assert by_title(results, "Required files").status == "fail"  # no *.h
    makefile = by_title(results, "Makefile rules")
    assert makefile.status == "fail" and "fclean" in makefile.detail and "re" in makefile.detail
    assert by_title(results, "build artifacts").status == "warn"
    secrets = by_title(results, "secrets")
    assert secrets.status == "fail" and any(e.file == ".env" for e in secrets.evidence)


def test_manual_rules_are_reported_as_manual():
    spec_pages = SUBJECT_PAGES
    spec = parse_subject("x.pdf", spec_pages)
    manual = [r for r in spec.rules if r.kind == "manual"]
    assert manual, "expected the 'never crash' sentence to be kept as a manual rule"


@pytest.mark.skipif(shutil.which("make") is None or shutil.which("cc") is None, reason="needs make and cc")
def test_dynamic_checks_good_repo(good_repo, local_sandbox):
    results = review(good_repo, local_sandbox)
    assert by_title(results, "`push_swap`").status == "pass"
    flags = by_title(results, "-Wall -Wextra -Werror")
    assert flags.status == "pass", flags.detail
    assert by_title(results, "does not relink").status == "pass"
    assert by_title(results, "`make clean` removes objects").status == "pass"
    assert by_title(results, "`make fclean` removes everything").status == "pass"
    assert by_title(results, "`make re` rebuilds").status == "pass"
    assert (good_repo / "push_swap").is_file()  # left in the built state


@pytest.mark.skipif(shutil.which("make") is None or shutil.which("cc") is None, reason="needs make and cc")
def test_dynamic_checks_bad_repo(bad_repo, local_sandbox):
    results = review(bad_repo, local_sandbox)
    flags = by_title(results, "-Wall -Wextra -Werror")
    assert flags.status == "fail" and flags.evidence
    assert by_title(results, "does not relink").status in ("fail", "skipped", "pass")


def test_the_text_requirements_run_inside_the_whole_review_and_show_up_as_lacking_or_second_look(tmp_path):
    """From a subject's text to the verdict: the parsed rules go through run_checks, and the buckets of verdict.md."""
    from verdict.reports.report import bucket
    pages = ["Chapter V\nMandatory part\nProgram Name\nft_ping\nDescription\nYou must code in C and submit a Makefile.\n"
             "You only have to submit a signature.txt file at the root of your repository.\n"
             "You must write a program that does what the original does.\n"]
    spec = parse_subject("ft_ping.pdf", pages)
    repo = project(tmp_path, "ft_ping.c", "docs/signature.txt")                                                # no Makefile, signature.txt not at the root
    results = []
    run_checks(Ctx(repo=repo.resolve(), rules=spec.rules, sandbox=None, lang=spec.lang), results.append)
    named = by_title(results, "Required files named in the subject")
    assert named.status == "fail" and "Makefile" in named.detail and "signature.txt" in named.detail
    assert [e.title for e in bucket(results, None).lacking if e.title.startswith("Required files named")]


# ---------------------------------------------------------------- files added for the evaluation


def test_files_added_for_the_evaluation_are_never_flagged(tmp_path):
    repo = project(tmp_path, ["Makefile", "main.c", "philo.h", "tests/run.sh", "tests/cases/a.txt", "tester.py", "Dockerfile",
                              "mlx/test.sh"])
    spec = parse_subject("philosophers.pdf", ["Chapter I\nMandatory part\nYour project must be written in C.\n"])
    results: list[CheckResult] = []
    run_checks(Ctx(repo=repo.resolve(), rules=spec.rules, sandbox=None, lang="c"), results.append)
    assert not any("evaluation" in (r.title + r.detail).lower() for r in results)        # no item, no mention
    language = next(r for r in results if r.title == "Written in C")
    assert language.status == "pass" and "test scripts" in language.detail and "allowed" not in language.detail
