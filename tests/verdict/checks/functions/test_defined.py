"""The functions the subject lists must be in the library `make` builds, not only in the sources."""

import shutil

import pytest

from tests.verdict.checks.helpers import by_title, review


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
