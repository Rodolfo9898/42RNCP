"""The layout of the files to turn in is binding only for libft, ft_printf and get_next_line."""

from tests.verdict.checks.helpers import check, files_rule, project


# ---------------------------------------------------------------- the layout is free outside the strict projects


def test_headers_in_include_and_sources_in_srcs_satisfy_any_wildcard_of_the_subject(tmp_path):
    repo = project(tmp_path, ["Makefile", "include/philo.h", "srcs/core/main.c"])
    assert check(repo, files_rule(["Makefile", "*.h", "*.c"])).status == "pass"
    assert check(repo, files_rule(["Makefile", "*/*.h", "*/*.c"])).status == "pass"         # deeper than one folder still counts
    nothing = check(project(tmp_path / "b", ["Makefile", "include/philo.h"]), files_rule(["Makefile", "*.h", "*.c"]))
    assert nothing.status == "fail" and "Missing: *.c" in nothing.detail                    # the files must still exist


def test_a_file_in_another_place_than_the_subject_shows_passes_outside_the_strict_projects(tmp_path):
    repo = project(tmp_path, ["docs/signature.txt", "Makefile"])
    loose = check(repo, files_rule(["signature.txt"], root=["signature.txt"]))
    assert loose.status == "pass" and "`docs/signature.txt`" in loose.detail and "layout is free" in loose.detail
    strict = check(repo, files_rule(["signature.txt"], pdf="get_next_line.pdf", root=["signature.txt"]))
    assert strict.status == "fail" and "belongs at the root" in strict.detail


def test_the_strict_projects_keep_their_format(tmp_path):
    gnl = ["get_next_line.c", "get_next_line_utils.c", "get_next_line.h"]
    nested = project(tmp_path, [f"src/{f}" for f in gnl])
    assert check(nested, files_rule(gnl, pdf="get_next_line.pdf", root=gnl)).status == "fail"
    libft = project(tmp_path / "libft", ["Makefile", "includes/libft.h", "ft_strlen.c"])
    assert check(libft, files_rule(["Makefile", "libft.h", "ft_*.c"], pdf="libft.pdf")).status == "warn"


def test_required_files_that_only_appear_after_make_count(tmp_path, local_sandbox):
    repo = project(tmp_path, {"Makefile": "all:\n\tmkdir -p libft && touch libft/libft.h libft/Makefile\n", "main.c": "x\n"})
    r = check(repo, files_rule(["Makefile", "libft/libft.h"], pdf="so_long.pdf"), sandbox=local_sandbox)
    assert r.status == "pass" and "once `make` has run" in r.detail
