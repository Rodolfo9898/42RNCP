import sys

import pytest

from tests.conftest import SUBJECT_PAGES
from tests.verdict.checks.helpers import by_title, review


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
