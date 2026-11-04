import shutil
import sys

import pytest

from verdict.checks import Ctx, run_checks, strip_code
from verdict.checks.dynamic import build_unit, makefile_behavior, no_crash, no_leaks
from verdict.models import Rule
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


def graphics_subject():
    """A subject like fract-ol's: the math library and MiniLibX are allowed as a whole."""
    pages = list(SUBJECT_PAGES)
    pages[2] = pages[2].replace(
        "- read, write, malloc, free,\nexit\n",
        "- read, write, malloc, free,\nexit\n- All functions of the math\nlibrary (-lm compiler option,\n"
        "man 3 math).\n- All functions of the MiniLibX\nlibrary.\n")
    return pages


def linked_repo(tmp_path, own_code, library_code="int\tlib_helper(void)\n{\n\treturn (0);\n}\n"):
    """A program linked with a vendored minilibx-linux/ library, which the checks do not review."""
    repo = tmp_path / "linked"
    (repo / "minilibx-linux").mkdir(parents=True)
    (repo / "minilibx-linux" / "lib.c").write_text(library_code)
    (repo / "main.c").write_text(own_code)
    (repo / "Makefile").write_text(
        "NAME = push_swap\nall: $(NAME)\n$(NAME): main.c minilibx-linux/lib.c\n"
        "\tcc -Wall -Wextra -Werror main.c minilibx-linux/lib.c -lm -o $(NAME)\n"
        "clean:\n\trm -f main.o\nfclean: clean\n\trm -f $(NAME)\nre: fclean all\n")
    return repo


MATH_MAIN = """#include <math.h>

int\tlib_helper(void);

int\tmain(int argc, char **argv)
{
\tvolatile double\tx;

\t(void)argv;
\tx = argc;
\treturn ((int)(fma(x, x, -x) + fmin(x, 2.0) + fmax(x, 2.0) + copysign(x, 1.0)) + lib_helper());
}
"""


@pytest.mark.skipif(sys.platform != "linux", reason="symbol names differ outside Linux")
def test_every_function_of_the_math_library_is_allowed_when_the_subject_allows_it(tmp_path, local_sandbox):
    repo = linked_repo(tmp_path, MATH_MAIN)
    fn = by_title(review(repo, local_sandbox, graphics_subject()), "authorized external functions")
    assert fn.status == "pass", fn.detail


@pytest.mark.skipif(sys.platform != "linux", reason="symbol names differ outside Linux")
def test_the_math_library_is_still_refused_when_the_subject_does_not_allow_it(tmp_path, local_sandbox):
    repo = linked_repo(tmp_path, MATH_MAIN)
    fn = by_title(review(repo, local_sandbox), "authorized external functions")
    assert fn.status == "fail" and "fma" in fn.detail


@pytest.mark.skipif(sys.platform != "linux", reason="symbol names differ outside Linux")
def test_what_a_linked_library_uses_internally_is_not_held_against_the_project(tmp_path, local_sandbox):
    library = '#include <stdlib.h>\n#include <string.h>\n\nint\tlib_helper(void)\n{\n' \
        '\tconst char\t*home;\n\n\thome = getenv("HOME");\n\tif (!home)\n\t\treturn (0);\n' \
        '\treturn ((int)strlen(home));\n}\n'
    own = "int\tlib_helper(void);\n\nint\tmain(void)\n{\n\treturn (lib_helper());\n}\n"
    repo = linked_repo(tmp_path, own, library)
    fn = by_title(review(repo, local_sandbox, graphics_subject()), "authorized external functions")
    assert fn.status == "pass", fn.detail
    assert "linked libraries" in fn.detail


@pytest.mark.skipif(sys.platform != "linux", reason="symbol names differ outside Linux")
def test_only_the_functions_the_project_itself_calls_are_named_as_forbidden(tmp_path, local_sandbox):
    library = '#include <stdlib.h>\n\nint\tlib_helper(void)\n{\n' \
        '\treturn (getenv("HOME") != 0);\n}\n'
    own = '#include <string.h>\n\nint\tlib_helper(void);\n\nint\tmain(int argc, char **argv)\n{\n' \
        '\t(void)argc;\n\treturn ((int)strlen(argv[0]) + lib_helper());\n}\n'
    repo = linked_repo(tmp_path, own, library)
    fn = by_title(review(repo, local_sandbox, graphics_subject()), "authorized external functions")
    assert fn.status == "fail"
    assert "strlen" in fn.detail and "getenv" not in fn.detail
    assert any(e.file == "main.c" for e in fn.evidence)
    assert not any(e.file.startswith("minilibx-linux/") for e in fn.evidence)


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


# ---------------------------------------------------------------- Required files: the root or a subfolder, and "elsewhere" is a second look


def files_result(repo, listing, pdf="ft_printf.pdf", page=8):
    from verdict.checks.static import required_files
    from verdict.models import Rule, Source
    from verdict.spec import expand_files
    required, notes = expand_files(listing)
    rule = Rule(id="rf", kind="required_files", title="Required files", params={"files": required, "notes": notes}, sources=[Source(pdf=pdf, page=page)])
    return list(required_files(Ctx(repo=repo.resolve(), rules=[rule], sandbox=None, lang="c"), rule))[0]


FT_PRINTF = "Makefile, *.h, */*.h, *.c, */*.c"


def project(tmp_path, *files):
    repo = tmp_path / "proj"
    for name in files:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")
    repo.mkdir(exist_ok=True)
    return repo


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
    from verdict.report import bucket
    r = files_result(project(tmp_path, "Makefile", "includes/libft.h", "ft_strlen.c"), "Makefile, libft.h, ft_*.c", "libft.pdf", 4)
    buckets = bucket([r], None)
    assert [e.title for e in buckets.second] == [r.title] and buckets.lacking == []


# ---------------------------------------------------------------- required files named in the subject's text: folders, "at the root", example layouts


def rule_result(repo, files, *, root=(), soft=(), notes=()):
    from verdict.checks.static import required_files
    from verdict.models import Rule, Source
    params = {"files": [[f] for f in files], "notes": list(notes), "from_text": True,
              **({"root": list(root)} if root else {}), **({"soft": list(soft)} if soft else {})}
    rule = Rule(id="rf2", kind="required_files", title="Required files named in the subject", params=params, sources=[Source(pdf="x.pdf", page=5)])
    return list(required_files(Ctx(repo=repo.resolve(), rules=[rule], sandbox=None, lang="c"), rule))[0]


def test_a_makefile_the_subject_asks_for_in_its_text_is_checked(tmp_path):
    assert rule_result(project(tmp_path / "a", "Makefile", "main.c"), ["Makefile"]).status == "pass"
    r = rule_result(project(tmp_path / "b", "main.c"), ["Makefile"])
    assert r.status == "fail" and "Missing: Makefile." in r.detail and r.title == "Required files named in the subject"


def test_a_file_the_subject_wants_at_the_root_must_be_there_not_just_somewhere(tmp_path):
    assert rule_result(project(tmp_path / "a", "signature.txt"), ["signature.txt"], root=["signature.txt"]).status == "pass"
    r = rule_result(project(tmp_path / "b", "docs/signature.txt"), ["signature.txt"], root=["signature.txt"])
    assert r.status == "fail" and "`docs/signature.txt`" in r.detail and "belongs at the root" in r.detail      # (without root it would be a second look)
    assert rule_result(project(tmp_path / "c", "docs/signature.txt"), ["signature.txt"]).status == "warn"


def test_wildcards_that_must_be_at_the_root_do_not_match_the_subfolders(tmp_path):
    get_next_line = ["get_next_line.c", "get_next_line_utils.c", "get_next_line.h"]
    assert rule_result(project(tmp_path / "a", *get_next_line), get_next_line, root=get_next_line).status == "pass"
    nested = project(tmp_path / "b", *[f"src/{f}" for f in get_next_line])
    r = rule_result(nested, get_next_line, root=get_next_line)
    assert r.status == "fail" and "belongs at the root" in r.detail
    sources = project(tmp_path / "c", "src/a.c", "main.c")
    assert rule_result(sources, ["*.c"], root=["*.c"]).status == "pass"                                       # main.c is at the root
    assert rule_result(project(tmp_path / "d", "src/a.c"), ["*.c"], root=["*.c"]).status == "fail"            # only in a subfolder
    assert rule_result(project(tmp_path / "e", "src/a.c"), ["*.c"]).status == "pass"                          # no root rule: anywhere is fine


def test_a_folder_the_subject_lists_has_to_be_a_folder(tmp_path):
    assert rule_result(project(tmp_path / "a", "src/main.c", "static/app.css"), ["src/", "static/"]).status == "pass"
    r = rule_result(project(tmp_path / "b", "src/main.c", "static"), ["src/", "static/"])                      # `static` is a file here
    assert r.status == "fail" and "Missing: static/." in r.detail
    elsewhere = rule_result(project(tmp_path / "c", "app/src/main.c"), ["src/"])
    assert elsewhere.status == "warn" and "`app/src/`" in elsewhere.detail


def test_names_that_only_an_example_layout_shows_are_a_second_look_never_a_failure(tmp_path):
    r = rule_result(project(tmp_path, "Makefile"), ["Makefile", "secrets/", "srcs/docker-compose.yml"], soft=["secrets/", "srcs/docker-compose.yml"])
    assert r.status == "warn" and "only shows these in an example layout" in r.detail and "`secrets/`" in r.detail
    assert "Missing" not in r.detail
    complete = rule_result(project(tmp_path / "ok", "Makefile", "secrets/db.txt", "srcs/docker-compose.yml"), ["Makefile", "secrets/", "srcs/docker-compose.yml"],
                           soft=["secrets/", "srcs/docker-compose.yml"])
    assert complete.status == "pass"
    hard = rule_result(project(tmp_path / "bad", "secrets/db.txt"), ["Makefile", "secrets/"], soft=["secrets/"])
    assert hard.status == "fail" and "Missing: Makefile." in hard.detail                                       # what is asked outright still fails


def test_a_name_from_a_plain_ls_listing_is_only_a_hint(tmp_path):
    r = rule_result(project(tmp_path, "writeup1"), ["writeup1", "writeup2"], soft=["writeup1", "writeup2"])
    assert r.status == "warn" and "`writeup2`" in r.detail


def test_the_text_requirements_run_inside_the_whole_review_and_show_up_as_lacking_or_second_look(tmp_path):
    """From a subject's text to the verdict: the parsed rules go through run_checks, and the buckets of verdict.md."""
    from verdict.report import bucket
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


# A library project whose subject names no program (get_next_line): the fallback must not mistake objects for products.
ARCHIVE_MAKEFILE = """NAME = gnl.a

all: $(NAME)

$(NAME): gnl.o
\tar rcs $(NAME) gnl.o

gnl.o: gnl.c
\tcc -Wall -Wextra -Werror -c gnl.c -o gnl.o

clean:
\t{clean}

fclean:
\trm -f gnl.o $(NAME)

re: fclean all

.PHONY: all clean fclean re
"""


def archive_repo(tmp_path, clean="rm -f gnl.o"):
    (tmp_path / "Makefile").write_text(ARCHIVE_MAKEFILE.format(clean=clean))
    (tmp_path / "gnl.c").write_text("int\tgnl(void)\n{\n\treturn (0);\n}\n")
    return tmp_path


def behavior(repo, sandbox):
    return list(makefile_behavior(Ctx(repo=repo.resolve(), rules=[], sandbox=sandbox, lang="c")))


needs_build_tools = pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc") and shutil.which("ar")), reason="needs make, cc and ar")


@needs_build_tools
def test_make_clean_removing_objects_is_not_reported_as_removing_the_program(tmp_path, local_sandbox):
    results = behavior(archive_repo(tmp_path), local_sandbox)
    assert [r.status for r in results] == ["pass", "pass", "pass"], [r.detail for r in results]


@needs_build_tools
def test_make_clean_removing_the_library_is_still_reported(tmp_path, local_sandbox):
    results = behavior(archive_repo(tmp_path, clean="rm -f gnl.o gnl.a"), local_sandbox)
    assert "`make clean` keeps the program" in [r.title for r in results if r.status == "fail"]
    assert any("gnl.a" in r.detail and "gnl.o" not in r.detail for r in results if r.status == "fail")


@needs_build_tools
def test_make_clean_removing_an_executable_is_still_reported(good_repo, local_sandbox):
    makefile = good_repo / "Makefile"
    makefile.write_text(makefile.read_text().replace("clean:\n\trm -f $(OBJS)\n", "clean:\n\trm -f $(OBJS) $(NAME)\n"))
    fails = [r for r in behavior(good_repo, local_sandbox) if r.status == "fail"]
    assert any(r.title == "`make clean` keeps the program" and "push_swap" in r.detail for r in fails)


@needs_build_tools
def test_objects_and_libraries_are_not_executables(tmp_path, local_sandbox):
    repo = archive_repo(tmp_path)
    ctx = Ctx(repo=repo.resolve(), rules=[], sandbox=local_sandbox, lang="c")
    assert ctx.build(".").ok and (repo / "gnl.o").is_file()
    assert ctx.executables(".") == []
    assert [p.name for p in ctx.libraries(".")] == ["gnl.a"]


@needs_build_tools
def test_shared_libraries_are_not_executables(tmp_path, local_sandbox):
    (tmp_path / "lib.c").write_text("int\tf(void)\n{\n\treturn (0);\n}\n")
    assert local_sandbox.exec(["cc", "-shared", "-fPIC", "lib.c", "-o", "libf.so"], tmp_path).ok
    ctx = Ctx(repo=tmp_path.resolve(), rules=[], sandbox=local_sandbox, lang="c")
    assert ctx.executables(".") == []
    assert [p.name for p in ctx.libraries(".")] == ["libf.so"]


@needs_build_tools
def test_runtime_checks_skip_a_library_instead_of_running_its_objects(tmp_path, local_sandbox):
    rules = [Rule(id=kind, kind=kind, title=kind, text="", section="mandatory", sources=[]) for kind in ("no_crash", "no_leaks")]
    ctx = Ctx(repo=archive_repo(tmp_path).resolve(), rules=rules, sandbox=local_sandbox, lang="c")
    assert [r.status for r in no_crash(ctx, rules[0])] == ["skipped"]
    assert [r.status for r in no_leaks(ctx, rules[1])] == ["skipped"]


@needs_build_tools
def test_build_unit_counts_a_library_but_not_bare_objects(tmp_path, local_sandbox):
    rule = Rule(id="b", kind="build_unit", title="b", text="", section="mandatory", sources=[])
    repo = archive_repo(tmp_path)
    built = list(build_unit(Ctx(repo=repo.resolve(), rules=[rule], sandbox=local_sandbox, lang="c"), rule))[0]
    assert built.status == "pass" and "gnl.a" in built.detail and "gnl.o" not in built.detail
    (repo / "Makefile").write_text("all:\n\tcc -c gnl.c -o gnl.o\n")
    (repo / "gnl.a").unlink()
    (repo / "gnl.o").unlink()
    assert list(build_unit(Ctx(repo=repo.resolve(), rules=[rule], sandbox=local_sandbox, lang="c"), rule))[0].status == "warn"
