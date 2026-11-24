"""Required files: the root or a subfolder, and "elsewhere" is a second look."""

import pytest

from verdict.checks.files.required import RequiredFilesChecker
from verdict.core.models import Rule, Source
from verdict.subjects.spec import expand_files

from tests.verdict.checks.helpers import answer, project


def files_result(repo, listing, pdf="ft_printf.pdf", page=8):
    required, notes = expand_files(listing)
    rule = Rule(id="rf", kind="required_files", title="Required files", params={"files": required, "notes": notes}, sources=[Source(pdf=pdf, page=page)])
    return answer(RequiredFilesChecker(), repo, rule)


FT_PRINTF = "Makefile, *.h, */*.h, *.c, */*.c"


def test_everything_at_the_root_satisfies_a_list_that_allows_the_root_or_a_subfolder(tmp_path):
    r = files_result(project(tmp_path, "Makefile", "ft_printf.h", "ft_printf.c"), FT_PRINTF)
    assert r.status == "pass" and "Missing" not in r.detail                              # the reported bug: "Missing: */*.h, */*.c"


def test_sources_in_a_subfolder_or_deeper_also_satisfy_it(tmp_path):
    assert files_result(project(tmp_path, "Makefile", "includes/ft_printf.h", "src/ft_printf.c"), FT_PRINTF).status == "pass"
    deeper = project(tmp_path / "deep", "Makefile", "include/a/ft_printf.h", "src/utils/ft_printf.c")
    assert files_result(deeper, FT_PRINTF).status == "pass"


def test_no_source_anywhere_is_still_missing(tmp_path):
    r = files_result(project(tmp_path, "Makefile", "ft_printf.h"), FT_PRINTF)
    assert r.status == "fail" and "Missing: *.c or */*.c" in r.detail and "*.h" not in r.detail.split("Missing:")[1].split(".")[0]


def test_a_required_file_that_sits_elsewhere_is_a_second_look_not_a_failure(tmp_path):
    r = files_result(project(tmp_path, "Makefile", "includes/libft.h", "ft_strlen.c"), "Makefile, libft.h, ft_*.c", "libft.pdf", 4)
    assert r.status == "warn"
    assert "libft.h → `includes/libft.h`" in r.detail and "organise the project in subfolders" in r.detail and "Missing" not in r.detail
    assert r.sources[0].pdf == "libft.pdf" and r.sources[0].page == 4


def test_a_wildcard_pinned_to_one_folder_level_is_a_second_look_when_the_files_are_at_the_root(tmp_path):
    r = files_result(project(tmp_path, "main.c", "util.h"), "*/*.c, */*.h")
    assert r.status == "warn" and "`main.c`" in r.detail and "`util.h`" in r.detail


def test_something_truly_missing_still_fails_and_the_elsewhere_hint_rides_along(tmp_path):
    r = files_result(project(tmp_path, "includes/libft.h", "ft_strlen.c"), "Makefile, libft.h, ft_*.c", "libft.pdf", 4)
    assert r.status == "fail" and "Missing: Makefile." in r.detail and "libft.h → `includes/libft.h`" in r.detail


def test_vendored_folders_do_not_count_as_elsewhere(tmp_path):
    vendored = files_result(project(tmp_path, "Makefile", "minilibx/libft.h", "ft_x.c"), "Makefile, libft.h, ft_*.c", "libft.pdf", 4)
    assert vendored.status == "fail" and "Missing: libft.h." in vendored.detail


def test_a_file_with_the_wrong_letter_case_is_still_pointed_out(tmp_path):
    probe = tmp_path / "CaseProbe"
    probe.write_text("x")
    if (tmp_path / "caseprobe").exists():
        pytest.skip("this disk does not tell Makefile from makefile (the Linux sandbox does)")
    cased = files_result(project(tmp_path / "b", "makefile", "libft.h", "ft_x.c"), "Makefile, libft.h, ft_*.c", "libft.pdf", 4)
    assert cased.status == "fail" and "different letter case" in cased.detail


def test_a_second_look_result_lands_under_second_look_in_the_verdict_and_not_under_lacking(tmp_path):
    from verdict.reports.report import bucket
    r = files_result(project(tmp_path, "Makefile", "includes/libft.h", "ft_strlen.c"), "Makefile, libft.h, ft_*.c", "libft.pdf", 4)
    buckets = bucket([r], None)
    assert [e.title for e in buckets.second] == [r.title] and buckets.lacking == []
