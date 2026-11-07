"""How the evaluator reads a subject (shared.evaluation_rules): the checks follow these rules, and every prompt repeats them.

- "Copy X into your repository" is met by any way of getting it there (a submodule, a download by the Makefile).
- MiniLibX is given to the students: no Norm for it, whatever its folder is called.
- The layout of the files to turn in is binding only for libft, ft_printf and get_next_line.
- Files added for the evaluation (tests, scripts, Docker) are allowed, but must work.
"""

from pathlib import Path

from verdict import ai
from verdict.checks import Ctx, minilibx_dirs, run_checks
from verdict.checks.static import evaluation_extras, libft_copy, required_files
from verdict.models import CheckResult, Rule, Source
from verdict.prompts import build_fix_prompt, build_review_prompt
from verdict.repo import tracked_files
from verdict.shared import evaluation_rules, strict_layout
from verdict.spec import parse_subject

HEADER = """/* ************************************************************************** */
/*                                                                            */
/*   ft_strlen.c                                        :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: student <student@student.42.fr>            +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2025/01/01 00:00:00 by student          #+#    #+#             */
/*   Updated: 2025/01/01 00:00:00 by student         ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */
"""


def project(root: Path, files: dict[str, str] | list[str]) -> Path:
    items = files.items() if isinstance(files, dict) else ((name, "x\n") for name in files)
    for name, text in items:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    root.mkdir(parents=True, exist_ok=True)
    return root


def files_rule(files, *, pdf="philosophers.pdf", unit=".", root=(), section="mandatory") -> Rule:
    params = {"files": [[f] if isinstance(f, str) else f for f in files], "notes": [], **({"root": list(root)} if root else {})}
    return Rule(id=f"rf-{unit}", kind="required_files", title="Required files", section=section, unit=unit, params=params,
                sources=[Source(pdf=pdf, page=3)])


def check(repo: Path, rule: Rule, rules=None, sandbox=None) -> CheckResult:
    ctx = Ctx(repo=repo.resolve(), rules=rules or [rule], sandbox=sandbox, lang="c")
    return list(required_files(ctx, rule))[0]


# ---------------------------------------------------------------- which projects are strict


def test_only_libft_ft_printf_and_get_next_line_have_a_binding_layout():
    for name in ("libft.pdf", "ft_printf.pdf", "get_next_line.pdf", "en.libft.subject.pdf"):
        assert strict_layout([name]), name
    for name in ("philosophers.pdf", "so_long.pdf", "minishell.pdf", "push_swap.pdf", "en.norm.pdf"):
        assert not strict_layout([name]), name
    assert "respect the subject's format exactly" in evaluation_rules(["libft.pdf"])
    loose = evaluation_rules(["philosophers.pdf"])
    assert "DRY" in loose and "include/" in loose and "submodule" in loose and "MiniLibX" in loose and "must work" in loose


# ---------------------------------------------------------------- the layout is free outside the strict projects


def test_headers_in_include_and_sources_in_srcs_satisfy_any_wildcard_of_the_subject(tmp_path):
    repo = project(tmp_path, ["Makefile", "include/philo.h", "srcs/core/main.c"])
    assert check(repo, files_rule(["Makefile", "*.h", "*.c"])).status == "pass"
    assert check(repo, files_rule(["Makefile", "*/*.h", "*/*.c"])).status == "pass"         # deeper than one folder still counts
    nothing = check(project(tmp_path / "b", ["Makefile", "include/philo.h"]), files_rule(["Makefile", "*.h", "*.c"]))
    assert nothing.status == "fail" and "Missing: *.c" in nothing.detail                    # the files must still exist


def test_a_file_in_another_place_than_the_subject_shows_passes_outside_the_strict_projects(tmp_path):
    repo = project(tmp_path, ["docs/signature.txt", "Makefile"])
    loose = check(repo, files_rule(["signature.txt"], root=["signature.txt"]))
    assert loose.status == "pass" and "`docs/signature.txt`" in loose.detail and "layout is free" in loose.detail
    strict = check(repo, files_rule(["signature.txt"], pdf="get_next_line.pdf", root=["signature.txt"]))
    assert strict.status == "fail" and "belongs at the root" in strict.detail


def test_the_strict_projects_keep_their_format(tmp_path):
    gnl = ["get_next_line.c", "get_next_line_utils.c", "get_next_line.h"]
    nested = project(tmp_path, [f"src/{f}" for f in gnl])
    assert check(nested, files_rule(gnl, pdf="get_next_line.pdf", root=gnl)).status == "fail"
    libft = project(tmp_path / "libft", ["Makefile", "includes/libft.h", "ft_strlen.c"])
    assert check(libft, files_rule(["Makefile", "libft.h", "ft_*.c"], pdf="libft.pdf")).status == "warn"


def philo_rules():
    return [
        files_rule(["Makefile", "*.h", "*.c"], unit="philo"),
        Rule(id="p", kind="program", title="Builds philo", unit="philo", params={"program": "philo"}, sources=[Source(pdf="philosophers.pdf", page=8)]),
        files_rule(["Makefile", "*.h", "*.c"], unit="philo_bonus", section="bonus"),
        Rule(id="pb", kind="program", title="Builds philo_bonus", unit="philo_bonus", section="bonus",
             params={"program": "philo_bonus", "bonus_target": True}, sources=[Source(pdf="philosophers.pdf", page=10)]),
    ]


def test_shared_code_beats_the_subjects_folders_dry(tmp_path):
    """philo/ and philo_bonus/ in the subject; the project keeps one folder whose Makefile builds both."""
    repo = project(tmp_path, ["philo/Makefile", "philo/philo.h", "philo/main.c", "philo/main_bonus.c"])
    rules = philo_rules()
    ctx = Ctx(repo=repo.resolve(), rules=rules, sandbox=None, lang="c")
    assert ctx.unit_dir("philo_bonus") == (repo / "philo").resolve()
    assert ctx.units() == ["philo"]                                                      # built once, not twice
    bonus = list(required_files(ctx, rules[2]))[0]
    assert bonus.status == "pass" and "DRY" in bonus.detail and "`philo/`" in bonus.detail


def test_a_missing_folder_stays_missing_in_the_strict_projects_and_for_exercises(tmp_path):
    repo = project(tmp_path, ["ex00/Makefile", "ex00/main.cpp"])
    exercise = files_rule(["Makefile", "*.cpp"], unit="ex01", pdf="cpp00.pdf")
    rules = [exercise, Rule(id="b", kind="build_unit", title="ex01: compiles", unit="ex01", sources=[Source(pdf="cpp00.pdf", page=5)])]
    assert check(repo, exercise, rules).status == "fail"                                    # an exercise is its own work, not shared code
    strict = [r.model_copy(update={"sources": [Source(pdf="libft.pdf", page=1)]}) for r in philo_rules()]
    philo = project(tmp_path / "p", ["philo/Makefile", "philo/philo.h", "philo/main.c"])
    assert check(philo, strict[2], strict).status == "fail"


# ---------------------------------------------------------------- MiniLibX, whatever its folder is called


MLX = {"gfx/mlx_custom/mlx.h": "x\n", "gfx/mlx_custom/mlx_int.h": "x\n", "gfx/mlx_custom/mlx_init.c": "int a;\n",
       "deps/MLX42/include/MLX42/MLX42.h": "x\n", "deps/MLX42/src/mlx_window.c": "int b;\n"}


def test_minilibx_is_found_by_its_files_not_its_folder_name(tmp_path):
    repo = project(tmp_path, {**MLX, "src/main.c": "int main;\n", "include/so_long.h": "x\n", "mlx.h": "x\n", "mlx_tools.c": "x\n"})
    assert minilibx_dirs(repo, tracked_files(repo)) == ["deps/MLX42", "gfx/mlx_custom"]   # never the project's own root
    ctx = Ctx(repo=repo.resolve(), rules=[], sandbox=None, lang="c")
    sources = {p.as_posix() for p in ctx.source_files()}
    assert "src/main.c" in sources and not any(s.startswith(("gfx/", "deps/")) for s in sources)


def test_the_norm_result_says_minilibx_was_left_out(tmp_path, monkeypatch):
    from verdict.checks import dynamic
    repo = project(tmp_path, {**MLX, "src/main.c": "int main;\n"})
    rule = Rule(id="n", kind="norm", title="Passes norminette", sources=[Source(pdf="en.norm.pdf", page=1)])
    ctx = Ctx(repo=repo.resolve(), rules=[rule], sandbox=None, lang="c")
    seen = {}

    def fake_report(c):
        seen["files"] = [p.as_posix() for p in c.source_files(".")]
        return {"files": 1, "errors": {}, "available": True}

    monkeypatch.setattr(dynamic, "_norm_report", fake_report)
    res = list(dynamic.norm(ctx, rule))[0]
    assert res.status == "pass" and "`gfx/mlx_custom/`" in res.detail and "not written by them" in res.detail
    assert seen["files"] == ["src/main.c"]


def test_the_students_own_submodules_are_under_the_norm_but_minilibx_is_not(tmp_path):
    repo = project(tmp_path, {
        ".gitmodules": '[submodule "libft"]\n\tpath = libft\n\turl = git@github.com:me/libft.git\n'
                       '[submodule "mlx"]\n\tpath = minilib\n\turl = https://github.com/42Paris/minilibx-linux.git\n'
                       '[submodule "unity"]\n\tpath = vendor/unity\n\turl = https://github.com/ThrowTheSwitch/Unity.git\n',
        "libft/ft_strlen.c": HEADER + "int ft_strlen;\n", "libft/libft.h": HEADER,
        "minilib/mlx.h": "x\n", "minilib/mlx_init.c": "int a;\n",
        "vendor/unity/unity.c": "int u;\n",                                                 # third-party, no 42 header
        "main.c": "int main;\n",
    })
    ctx = Ctx(repo=repo.resolve(), rules=[], sandbox=None, lang="c")
    assert sorted(p.as_posix() for p in ctx.student_submodule_files()) == ["libft/ft_strlen.c", "libft/libft.h"]


# ---------------------------------------------------------------- "copy your libft into a libft folder"


def libft_rule():
    spec = parse_subject("so_long.pdf", ["Chapter III\nCommon Instructions\nIf your project allows you to use your libft, you must copy "
                                         "its sources and its associated Makefile into a libft folder.\n"])
    rules = [r for r in spec.rules if r.kind == "libft_copy"]
    assert rules, [r.kind for r in spec.rules]
    return rules[0]


def copy_result(repo, sandbox=None, rules=None):
    rule = libft_rule()
    return list(libft_copy(Ctx(repo=repo.resolve(), rules=[rule, *(rules or [])], sandbox=sandbox, lang="c"), rule))[0]


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


def test_required_files_that_only_appear_after_make_count(tmp_path, local_sandbox):
    repo = project(tmp_path, {"Makefile": "all:\n\tmkdir -p libft && touch libft/libft.h libft/Makefile\n", "main.c": "x\n"})
    r = check(repo, files_rule(["Makefile", "libft/libft.h"], pdf="so_long.pdf"), sandbox=local_sandbox)
    assert r.status == "pass" and "once `make` has run" in r.detail


# ---------------------------------------------------------------- files added for the evaluation


def test_files_added_for_the_evaluation_are_allowed_but_must_be_tried(tmp_path):
    repo = project(tmp_path, ["Makefile", "main.c", "philo.h", "tests/run.sh", "tests/cases/a.txt", "tester.py", "Dockerfile",
                              "mlx/test.sh"])
    assert evaluation_extras(Ctx(repo=repo.resolve(), rules=[], sandbox=None, lang="c")) == ["Dockerfile", "tester.py", "tests/"]
    spec = parse_subject("philosophers.pdf", ["Chapter I\nMandatory part\nYour project must be written in C.\n"])
    results: list[CheckResult] = []
    run_checks(Ctx(repo=repo.resolve(), rules=spec.rules, sandbox=None, lang="c"), results.append)
    extras = next(r for r in results if r.title == "Files added for the evaluation work")
    assert extras.status == "manual" and "must work" in extras.detail and "fails" in extras.detail
    language = next(r for r in results if r.title == "Written in C")
    assert language.status == "pass" and "test scripts" in language.detail


def test_no_extras_no_item(tmp_path):
    repo = project(tmp_path, ["Makefile", "main.c"])
    results: list[CheckResult] = []
    run_checks(Ctx(repo=repo.resolve(), rules=[], sandbox=None, lang="c"), results.append)
    assert not any(r.title == "Files added for the evaluation work" for r in results)


# ---------------------------------------------------------------- the prompts say the same


def test_every_prompt_carries_the_evaluators_rules():
    review, _ = build_review_prompt(project="philo", subjects=["philosophers.pdf"], lang="c", results=[])
    assert "HOW I READ THE SUBJECT" in review and "DRY" in review and "submodule" in review and "MiniLibX" in review
    strict, _ = build_review_prompt(project="libft", subjects=["libft.pdf"], lang="c", results=[])
    assert "respect the subject's format exactly" in strict
    failed = CheckResult(rule_id="x", title="Required files", status="fail", detail="Missing: philo_bonus/")
    fix, stats = build_fix_prompt(project="philo", subjects=["philosophers.pdf"], lang="c", results=[failed])
    assert stats["issues"] and "HOW THE EVALUATOR READS THE SUBJECT" in fix and "do not duplicate shared code" in fix
    assert "DRY" in ai._review_task([("r1", "x")], ["philosophers.pdf"]) and "DRY" in ai._analysis_task(["philosophers.pdf"], "s", [])
