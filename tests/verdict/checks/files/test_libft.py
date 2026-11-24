"""`copy the sources of your libft and its Makefile into a libft folder`."""

from verdict.checks.files.libft import LibftCopyChecker
from verdict.core.models import Rule, Source
from verdict.subjects.spec import parse_subject

from tests.verdict.checks.helpers import answer, project


# ---------------------------------------------------------------- "copy your libft into a libft folder"


def libft_rule():
    spec = parse_subject("so_long.pdf", ["Chapter III\nCommon Instructions\nIf your project allows you to use your libft, you must copy "
                                         "its sources and its associated Makefile into a libft folder.\n"])
    rules = [r for r in spec.rules if r.kind == "libft_copy"]
    assert rules, [r.kind for r in spec.rules]
    return rules[0]


def copy_result(repo, sandbox=None, rules=None):
    rule = libft_rule()
    return answer(LibftCopyChecker(), repo, rule, rules=[rule, *(rules or [])], sandbox=sandbox)


def test_the_libft_copy_rule_is_checked_not_left_to_a_human(tmp_path):
    assert copy_result(project(tmp_path / "none", ["Makefile", "main.c"])).status == "na"
    assert copy_result(project(tmp_path / "ok", ["Makefile", "libft/Makefile", "libft/libft.h", "libft/ft_strlen.c"])).status == "pass"
    renamed = copy_result(project(tmp_path / "renamed", ["Makefile", "libs/mylib/Makefile", "libs/mylib/inc/libft.h"]))
    assert renamed.status == "pass" and "`libs/mylib/`" in renamed.detail and "layout is free" in renamed.detail
    strict = Rule(id="s", kind="manual", title="x", sources=[Source(pdf="ft_printf.pdf", page=2)])
    assert copy_result(project(tmp_path / "strict", ["Makefile", "libs/mylib/Makefile", "libs/mylib/libft.h"]), rules=[strict]).status == "warn"
    missing = copy_result(project(tmp_path / "missing", {"Makefile": "LIBFT = libft/libft.a\nall:\n", "main.c": '#include "libft.h"\n'}))
    assert missing.status == "fail" and "Makefile" in missing.detail


def test_a_libft_submodule_counts_as_copied(tmp_path):
    repo = project(tmp_path, {".gitmodules": '[submodule "libft"]\n\tpath = libft\n\turl = git@github.com:me/libft.git\n',
                              "Makefile": "all:\n", "libft/Makefile": "all:\n", "libft/libft.h": "x\n"})
    r = copy_result(repo)
    assert r.status == "pass" and "git submodule" in r.detail


def test_a_libft_that_make_downloads_counts_once_make_has_run(tmp_path, local_sandbox):
    makefile = "all:\n\tmkdir -p libft && printf 'all:\\n' > libft/Makefile && touch libft/libft.h\n"
    repo = project(tmp_path, {"Makefile": makefile, "main.c": '#include "libft/libft.h"\n'})
    r = copy_result(repo, local_sandbox)
    assert r.status == "pass" and "once `make` has run" in r.detail


def test_the_libft_project_itself_is_not_asked_to_copy_itself(tmp_path):
    lib = Rule(id="p", kind="program", title="Builds libft.a", params={"program": "libft.a"}, sources=[Source(pdf="libft.pdf", page=4)])
    assert copy_result(project(tmp_path, ["Makefile", "libft.h", "ft_strlen.c"]), rules=[lib]).status == "na"
