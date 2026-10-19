import subprocess
from pathlib import Path

import pymupdf
import pytest

from verdict.sandbox import ExecResult


class LocalSandbox:
    """Runs commands directly. Only ever used on fixture projects written by the tests."""

    def exec(self, argv, cwd, timeout=60, stdin=""):
        try:
            p = subprocess.run(argv, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return ExecResult(rc=-9, timed_out=True)
        except FileNotFoundError as exc:
            return ExecResult(rc=127, stderr=str(exc))
        return ExecResult(rc=p.returncode, stdout=p.stdout, stderr=p.stderr)


@pytest.fixture
def local_sandbox():
    return LocalSandbox()


GOOD_MAKEFILE = """NAME = push_swap
CC = cc
CFLAGS = -Wall -Wextra -Werror
SRCS = main.c
OBJS = $(SRCS:.c=.o)

all: $(NAME)

$(NAME): $(OBJS)
\t$(CC) $(CFLAGS) $(OBJS) -o $(NAME)

%.o: %.c
\t$(CC) $(CFLAGS) -c $< -o $@

clean:
\trm -f $(OBJS)

fclean: clean
\trm -f $(NAME)

re: fclean all

.PHONY: all clean fclean re
"""

MAIN_C = '#include <unistd.h>\n\nint\tmain(void)\n{\n\twrite(1, "ok\\n", 3);\n\treturn (0);\n}\n'


@pytest.fixture
def good_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "good"
    repo.mkdir()
    (repo / "Makefile").write_text(GOOD_MAKEFILE)
    (repo / "main.c").write_text(MAIN_C)
    (repo / "push_swap.h").write_text("#ifndef PUSH_SWAP_H\n# define PUSH_SWAP_H\n#endif\n")
    return repo


@pytest.fixture
def bad_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "bad"
    repo.mkdir()
    (repo / "Makefile").write_text("NAME = push_swap\nall:\n\tgcc main.c -o $(NAME)\nclean:\n\trm -f $(NAME)\n")
    (repo / "main.c").write_text(MAIN_C)
    (repo / "bad.c").write_text('#include <stdio.h>\n\nint g_count;\n\nint helper(void)\n{\n\tprintf("hi\\n");\n\treturn (g_count);\n}\n')
    (repo / ".env").write_text("TOKEN=abc\n")
    (repo / "junk.o").write_bytes(b"\x7fELF" + b"\0" * 16)
    return repo


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(40, 40, 550, 800), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


SUBJECT_PAGES = [
    "Contents\nI\nIntroduction\n2\nII\nMandatory part\n3\n",
    "Chapter I\nCommon Instructions\n"
    "- Your project must be written in C.\n"
    "- Your project must be written in accordance with the Norm.\n"
    "- Global variables are forbidden.\n"
    "- You must compile with the flags -Wall, -Wextra, and -Werror, using cc.\n"
    "- Your Makefile must not perform unnecessary relinking.\n"
    "- Your Makefile must contain at least the rules $(NAME), all, clean, fclean and re.\n"
    "- Your program must never crash.\n"
    "- Your functions must return the documented value for every valid input.\n"
    "- Your program must display an error message on the standard error for invalid input.\n"
    "- The unit tests provided by the school must never be modified.\n",
    "Chapter II\nMandatory part\nProgram Name\npush_swap\nFiles to Submit\nMakefile, *.h, *.c\n"
    "Makefile\nNAME, all, clean, fclean, re\nArguments\nstack a: A list of integers\n"
    "External Function\n- read, write, malloc, free,\nexit\n- ft_printf or any equivalent\n"
    "YOU coded\nLibft authorized\nYes\nDescription\nSort stacks\n",
]


@pytest.fixture
def subject_pdf() -> bytes:
    return make_pdf(SUBJECT_PAGES)


@pytest.fixture(autouse=True)
def hermetic_ai_environment(monkeypatch):
    """Tests never depend on (or leak) the developer's real AI configuration."""
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_MAX_CHARS", "LLM_STREAM", "LLM_FALLBACK_MODELS",
                 "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "TERMINAL_URL", "TERMINAL_TOKEN"):
        monkeypatch.delenv(name, raising=False)
