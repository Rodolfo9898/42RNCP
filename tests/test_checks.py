import shutil
import sys

import pytest

from verdict.checks import Ctx, run_checks, strip_code
from verdict.spec import parse_subject

from .conftest import SUBJECT_PAGES


def review(repo, sandbox=None, pages=SUBJECT_PAGES):
    spec = parse_subject("push_swap.pdf", pages)
    ctx = Ctx(repo=repo.resolve(), rules=spec.rules, sandbox=sandbox, lang=spec.lang)
    out = []
    run_checks(ctx, out.append)
    return out


def by_title(results, fragment):
    matches = [r for r in results if fragment in r.title]
    assert matches, f"no result titled like {fragment!r}: {[r.title for r in results]}"
    return matches[0]


def test_strip_code_blanks_comments_and_strings_but_keeps_lines():
    src = 'a(); // printf("x")\n/* free(p);\n */ b("malloc(", \'"\');\n'
    out = strip_code(src)
    assert out.count("\n") == src.count("\n")
    assert "printf" not in out and "free" not in out and "malloc" not in out
    assert "a();" in out and "b(" in out


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


@pytest.mark.skipif(sys.platform != "linux", reason="symbol names differ outside Linux")
def test_forbidden_function_is_reported_with_location(bad_repo, local_sandbox):
    results = review(bad_repo, local_sandbox)
    fn = by_title(results, "authorized external functions")
    assert fn.status == "fail" and any(e.file == "bad.c" and e.line == 7 for e in fn.evidence)


@pytest.mark.skipif(shutil.which("norminette") is None, reason="norminette not installed")
def test_norm_and_globals_use_norminette(bad_repo, local_sandbox):
    results = review(bad_repo, local_sandbox)
    assert by_title(results, "Passes norminette").status == "fail"
    assert by_title(results, "No global variables").status == "fail"


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


# ---------------------------------------------------------------- functions must be in the BUILT library, not only in the sources

LIB_SUBJECT = [
    "Chapter I\nMandatory part\nProgram Name\nlibft.a\nFiles to Submit\nMakefile, libft.h, ft_*.c\nMakefile\nNAME, all, clean, fclean, re\nDescription\nx\n"
    "Function Name\nft_one\nFiles to Submit\n-\nDescription\nx\nFunction Name\nft_two\nFiles to Submit\n-\nDescription\nx\n"
]
LIB_MAKEFILE = "NAME = libft.a\nSRCS = ft_one.c\nOBJS = $(SRCS:.c=.o)\nall: $(NAME)\n$(NAME): $(OBJS)\n\tar rc $(NAME) $(OBJS)\n%.o: %.c\n\tcc -Wall -Wextra -Werror -c $< -o $@\nclean:\n\trm -f $(OBJS)\nfclean: clean\n\trm -f $(NAME)\nre: fclean all\n.PHONY: all clean fclean re\n"


def library_repo(tmp_path, makefile=LIB_MAKEFILE):
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "libft.h").write_text("#ifndef LIBFT_H\n# define LIBFT_H\nint ft_one(void);\nint ft_two(void);\n#endif\n")
    (tmp_path / "ft_one.c").write_text("int\tft_one(void)\n{\n\treturn (1);\n}\n")
    (tmp_path / "ft_two.c").write_text("int\tft_two(void)\n{\n\treturn (2);\n}\n")   # in the sources, but not in SRCS
    return tmp_path


@pytest.mark.skipif(shutil.which("make") is None or shutil.which("cc") is None or shutil.which("nm") is None, reason="needs make, cc and nm")
def test_a_function_missing_from_the_built_library_is_a_failure(tmp_path, local_sandbox):
    results = review(library_repo(tmp_path), local_sandbox, pages=LIB_SUBJECT)
    check = by_title(results, "Required functions are in libft.a")
    assert check.status == "fail" and "ft_two" in check.detail and "ft_one" not in check.detail
    assert "NOT in the libft.a that `make` builds" in check.detail


@pytest.mark.skipif(shutil.which("make") is None or shutil.which("cc") is None or shutil.which("nm") is None, reason="needs make, cc and nm")
def test_all_functions_in_the_built_library_pass(tmp_path, local_sandbox):
    fixed = LIB_MAKEFILE.replace("SRCS = ft_one.c", "SRCS = ft_one.c ft_two.c")
    check = by_title(review(library_repo(tmp_path, fixed), local_sandbox, pages=LIB_SUBJECT), "Required functions are in libft.a")
    assert check.status == "pass" and "present in libft.a" in check.detail


def test_without_a_sandbox_only_the_sources_can_be_checked(tmp_path):
    results = review(library_repo(tmp_path), None, pages=LIB_SUBJECT)
    check = by_title(results, "Required functions are defined")
    assert check.status == "pass" and "sources" in check.detail and "libft.a" not in check.detail


def test_a_missing_bonus_rule_is_not_applicable_when_there_are_no_bonus_files(tmp_path):
    from verdict.models import Rule
    (tmp_path / "Makefile").write_text("all:\n\tcc main.c\n")
    (tmp_path / "main.c").write_text("int main(void) { return 0; }\n")
    rule = Rule(id="r1", kind="bonus_rule", title="Makefile has a bonus rule")
    out = []
    run_checks(Ctx(repo=tmp_path.resolve(), rules=[rule], sandbox=None, lang="c"), out.append)
    assert [r.status for r in out if r.rule_id == "r1"] == ["na"]
