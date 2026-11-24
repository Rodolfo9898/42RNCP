import json

import pytest

from shared import constants
from shared.constants import (
    EVALUATOR, GENERATED_VERDICT_NAMES, HEADER_AUTHOR, OBEY, SKIPPED_NAMES, SUBJECT_NAME, TERMINAL_REPORTS_ROOT, TERMINAL_SUBJECTS_ROOT,
    UPDATE_BLOCK, VERDICT_MARKER, evaluation_rules, is_subject_name, strict_layout, verdict_update_rules,
)


def test_the_names_the_web_app_and_the_terminal_container_share_are_all_there():
    for name in ("EVALUATOR", "EVALUATOR_EMAIL", "HEADER_AUTHOR", "OBEY", "TEST_HERE", "UPDATE_BLOCK", "VERDICT_MARKER", "GENERATED_VERDICT_NAMES",
                 "SKIPPED_NAMES", "SUBJECT_NAME", "STRICT_LAYOUT", "TERMINAL_REPORTS_ROOT", "TERMINAL_SUBJECTS_ROOT", "evaluation_rules",
                 "is_subject_name", "strict_layout", "verdict_update_rules"):
        assert hasattr(constants, name), name


def test_the_header_author_is_the_evaluator_and_the_prompts_name_them():
    assert HEADER_AUTHOR.startswith(f"{EVALUATOR} <") and HEADER_AUTHOR.endswith(">")
    assert f"WHO GIVES THE ORDERS: {EVALUATOR}" in OBEY


@pytest.mark.parametrize("name,ok", [("libft.pdf", True), ("en.subject.pdf", True), ("My Subject.PDF", True), ("a/b.pdf", False),
                                     ("..pdf", False), ("x..y.pdf", False), ("notes.txt", False), (".pdf", False), ("a" * 120 + ".pdf", False)])
def test_a_subject_pdf_has_a_plain_name(name, ok):
    assert is_subject_name(name) is ok
    assert bool(SUBJECT_NAME.fullmatch(name)) or not ok


def test_the_folders_of_the_terminal_container_are_apart_and_the_generated_files_are_known():
    assert TERMINAL_SUBJECTS_ROOT != TERMINAL_REPORTS_ROOT
    assert VERDICT_MARKER.startswith("<!--") and "verdict.md" in GENERATED_VERDICT_NAMES and "claude-review.md" in GENERATED_VERDICT_NAMES
    assert ".claude" in SKIPPED_NAMES and "CLAUDE.md" in SKIPPED_NAMES


def test_the_shape_of_an_update_report_is_valid_json_and_the_rules_say_where_it_goes():
    block = json.loads(UPDATE_BLOCK)
    assert set(block) == {"fixes", "corrections", "improvements", "verdict"}
    rules = verdict_update_rules("`/scratch/reports/abc/claude-review.md`")
    assert "`/scratch/reports/abc/claude-review.md`" in rules and UPDATE_BLOCK in rules and '"fixes" key' in rules


def test_the_evaluators_reading_of_a_subject_is_in_every_version():
    assert "MiniLibX" in evaluation_rules([]) and "Copy X into your repository" in evaluation_rules(["so_long.pdf"])
    assert "Layout is not binding" in evaluation_rules(["so_long.pdf"])
    assert "must respect the subject's format exactly" in evaluation_rules(["libft.pdf"])


def test_only_libft_ft_printf_and_get_next_line_have_a_binding_layout():
    for name in ("libft.pdf", "ft_printf.pdf", "get_next_line.pdf", "en.libft.subject.pdf"):
        assert strict_layout([name]), name
    for name in ("philosophers.pdf", "so_long.pdf", "minishell.pdf", "push_swap.pdf", "en.norm.pdf"):
        assert not strict_layout([name]), name
    assert "respect the subject's format exactly" in evaluation_rules(["libft.pdf"])
    loose = evaluation_rules(["philosophers.pdf"])
    assert "DRY" in loose and "include/" in loose and "submodule" in loose and "MiniLibX" in loose and "never a finding" in loose
