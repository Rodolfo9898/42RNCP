"""What the checks tests share: small projects written to disk, and the review of one."""

import shutil
from pathlib import Path

import pytest

from verdict.checks import Ctx, run_checks
from verdict.checks.files.required import RequiredFilesChecker
from verdict.core.models import CheckResult, Rule, Source
from verdict.subjects.spec import parse_subject

from tests.conftest import SUBJECT_PAGES

needs_build_tools = pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc") and shutil.which("ar")), reason="needs make, cc and ar")


def project(root: Path, *files: str | list[str] | dict[str, str]) -> Path:
    """A project on disk: names (a file holding "x"), lists of names, or {name: text}."""
    for entry in files:
        items = entry.items() if isinstance(entry, dict) else ((name, "x\n") for name in ([entry] if isinstance(entry, str) else entry))
        for name, text in items:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    root.mkdir(parents=True, exist_ok=True)
    return root


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


def answer(checker, repo: Path, rule: Rule, *, rules=None, sandbox=None, lang="c", cache=None) -> CheckResult:
    """The first result `checker` gives for `rule` in the repository (the rules of the review default to this one)."""
    ctx = Ctx(repo=repo.resolve(), rules=rules or [rule], sandbox=sandbox, lang=lang, cache=cache if cache is not None else {})
    return list(checker.run(ctx, rule))[0]


def files_rule(files, *, pdf="philosophers.pdf", unit=".", root=(), section="mandatory") -> Rule:
    params = {"files": [[f] if isinstance(f, str) else f for f in files], "notes": [], **({"root": list(root)} if root else {})}
    return Rule(id=f"rf-{unit}", kind="required_files", title="Required files", section=section, unit=unit, params=params,
                sources=[Source(pdf=pdf, page=3)])


def check(repo: Path, rule: Rule, rules=None, sandbox=None) -> CheckResult:
    return answer(RequiredFilesChecker(), repo, rule, rules=rules, sandbox=sandbox)


# What a library project looks like once built: objects and an archive, but no program.
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


def fractol_like(tmp_path, makefile):
    """A project with a `libs/libft` submodule that was never downloaded (an empty folder), like the web app's clone of it."""
    repo = tmp_path / "fractol"
    (repo / "libs" / "libft").mkdir(parents=True)
    (repo / ".gitmodules").write_text('[submodule "libs/libft"]\n\tpath = libs/libft\n\turl = https://github.com/Rodolfo9898/libft.git\n')
    (repo / "Makefile").write_text(makefile)
    (repo / "main.c").write_text("int main(void)\n{\n\treturn (0);\n}\n")
    return repo


# MiniLibX under names that say nothing: found by the files it holds.
MLX = {"gfx/mlx_custom/mlx.h": "x\n", "gfx/mlx_custom/mlx_int.h": "x\n", "gfx/mlx_custom/mlx_init.c": "int a;\n",
       "deps/MLX42/include/MLX42/MLX42.h": "x\n", "deps/MLX42/src/mlx_window.c": "int b;\n"}
