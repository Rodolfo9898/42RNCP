"""The programs and units that must build, and a build that cannot be judged because it needs the network."""

from verdict.checks.make.products import BuildUnitChecker, ProgramChecker
from verdict.core.models import Rule
from verdict.repository.repo import SubmoduleNote

from tests.verdict.checks.helpers import answer, archive_repo, fractol_like, needs_build_tools


@needs_build_tools
def test_build_unit_counts_a_library_but_not_bare_objects(tmp_path, local_sandbox):
    rule = Rule(id="b", kind="build_unit", title="b", text="", section="mandatory", sources=[])
    repo = archive_repo(tmp_path)
    built = answer(BuildUnitChecker(), repo, rule, sandbox=local_sandbox)
    assert built.status == "pass" and "gnl.a" in built.detail and "gnl.o" not in built.detail
    (repo / "Makefile").write_text("all:\n\tcc -c gnl.c -o gnl.o\n")
    (repo / "gnl.a").unlink()
    (repo / "gnl.o").unlink()
    assert answer(BuildUnitChecker(), repo, rule, sandbox=local_sandbox).status == "warn"


# ---------------------------------------------------------------- a build that needs the network cannot be judged (the sandbox has none)


OFFLINE_LOG = ("fatal: unable to access 'https://github.com/Rodolfo9898/libft.git/': Could not resolve host: github.com\n"
               "fatal: clone of 'https://github.com/Rodolfo9898/libft.git' into submodule path '/work/libs/libft' failed\n"
               "make: *** [Makefile:40: submodules] Error 1\n")


def program_rule():
    return Rule(id="p", kind="program", title="fractol", text="", section="mandatory", sources=[], params={"program": "fractol"})


@needs_build_tools
def test_a_build_that_tried_to_download_something_is_a_warning_not_a_failure(tmp_path, local_sandbox):
    repo = fractol_like(tmp_path, f"all:\n\t@echo \"{OFFLINE_LOG.splitlines()[0]}\" >&2; exit 1\n")
    notes = [SubmoduleNote("libs/libft", False, "fatal: could not read Username for 'https://github.com'")]
    out = answer(ProgramChecker(), repo, program_rule(), sandbox=local_sandbox, cache={"submodule_notes": notes})
    assert out.status == "warn" and "sandbox has no network on purpose" in out.detail
    assert "libs/libft: fatal: could not read Username" in out.detail and "git submodule update --init" in out.detail
    assert "Could not resolve host" in out.log                                  # the evidence stays in the log


@needs_build_tools
def test_the_same_goes_for_a_library_build_and_without_notes_it_still_explains(tmp_path, local_sandbox):
    repo = fractol_like(tmp_path, "all:\n\t@echo \"fatal: unable to access 'https://github.com/x/y.git/': Could not resolve host: github.com\" >&2; exit 1\n")
    rule = Rule(id="b", kind="build_unit", title="b", text="", section="mandatory", sources=[])
    out = answer(BuildUnitChecker(), repo, rule, sandbox=local_sandbox)
    assert out.status == "warn" and "could not be checked" in out.detail and "download" in out.detail


@needs_build_tools
def test_a_missing_submodule_explains_a_failure_that_talks_about_it(tmp_path, local_sandbox):
    repo = fractol_like(tmp_path, "all:\n\t@echo 'main.c:1:10: fatal error: libs/libft/libft.h: No such file or directory' >&2; exit 1\n")
    out = answer(ProgramChecker(), repo, program_rule(), sandbox=local_sandbox)
    assert out.status == "warn" and "libs/libft" in out.detail and "not downloaded" in out.detail


@needs_build_tools
def test_a_build_that_fails_for_the_projects_own_reasons_is_still_a_failure_even_with_an_empty_submodule(tmp_path, local_sandbox):
    repo = fractol_like(tmp_path, "all:\n\t@echo 'main.c:3:5: error: expected ; before return' >&2; exit 1\n")
    out = answer(ProgramChecker(), repo, program_rule(), sandbox=local_sandbox)
    assert out.status == "fail" and out.detail == "The build failed."


@needs_build_tools
def test_a_plain_failure_without_any_submodule_is_a_failure(tmp_path, local_sandbox):
    repo = tmp_path / "plain"
    repo.mkdir()
    (repo / "Makefile").write_text("all:\n\t@echo 'nope' >&2; exit 1\n")
    assert answer(ProgramChecker(), repo, program_rule(), sandbox=local_sandbox).status == "fail"
