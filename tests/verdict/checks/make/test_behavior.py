"""`make clean`, `make fclean` and `make re` after a build."""

from verdict.checks import Ctx
from verdict.checks.make.behavior import MakefileBehavior

from tests.verdict.checks.helpers import archive_repo, needs_build_tools


def behavior(repo, sandbox):
    return list(MakefileBehavior().run(Ctx(repo=repo.resolve(), rules=[], sandbox=sandbox, lang="c")))


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
