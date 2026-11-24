"""How the evaluator reads a subject: the rules the checks follow and every prompt repeats."""

from __future__ import annotations

import re

# How this evaluator reads a subject. These are the evaluator's rules, and they win over a literal reading of the PDF: the checks
# follow them, and every prompt repeats them so that claude judges the same way.
#
# The format of the files to turn in is binding only for these projects (matched on the subject's file name).
STRICT_LAYOUT = re.compile(r"(^|[^a-z])(libft|ft_printf|get_next_line)([^a-z]|$)", re.IGNORECASE)


def strict_layout(subjects) -> bool:
    """Whether the required files must be exactly where and as the subject says (libft, ft_printf, get_next_line)."""
    return any(STRICT_LAYOUT.search(str(name)) for name in subjects)


def evaluation_rules(subjects) -> str:
    """The evaluator's reading of a subject, as bullet points for a prompt."""
    if strict_layout(subjects):
        layout = ("- This project is libft, ft_printf or get_next_line: here the files to turn in must respect the subject's format exactly "
                  "(names, and where they sit when the subject says so).")
    else:
        layout = ("- Layout is not binding in this project (it only is for libft, ft_printf and get_next_line). When the subject asks for a "
                  "structure (`*.h, *.c`, `*/*.h, */*.c`, \"all your files\", one folder per program such as philo/ and philo_bonus/), the "
                  "files must exist, but where they sit is free: headers in include/ and sources in srcs/ (or any subfolders) satisfy it, and "
                  "code shared between programs (the DRY principle) beats duplicating it to copy the subject's folders. Diverging from the "
                  "layout is never a problem by itself; work that is missing is.")
    return "\n".join([
        "- \"Copy X into your repository\" (for example the libft sources and Makefile into a libft folder) is met by any way of putting "
        "it there, a git submodule included, as long as the files are there once `make` has run.",
        "- MiniLibX (any version, whatever its folder is called) is provided to the students, not written by them: the Norm does not "
        "apply to it, and neither do findings about its code.",
        layout,
        "- Files added for the evaluation (a test suite, test scripts, tools, a Dockerfile or compose file that installs the dependencies, "
        "...) are expected and allowed, and they are meant to run in the environment you are given (the toolchain and the Docker setup). "
        "Their presence is never a finding, a doubt or an item for a human to judge: do not mention them in the report. Just run them "
        "directly (the test suite, the scripts, `docker build`, `docker compose up --build`) and use what they show. Only a failure of "
        "one of them is worth reporting, as the real problem it is.",
    ])
