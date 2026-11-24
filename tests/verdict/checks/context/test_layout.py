"""Which folder a rule applies to, and when the layout of the subject is binding."""

from verdict.checks import Ctx
from verdict.checks.files.required import RequiredFilesChecker
from verdict.core.models import Rule, Source

from tests.verdict.checks.helpers import check, files_rule, project


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
    bonus = list(RequiredFilesChecker().run(ctx, rules[2]))[0]
    assert bonus.status == "pass" and "DRY" in bonus.detail and "`philo/`" in bonus.detail


def test_a_missing_folder_stays_missing_in_the_strict_projects_and_for_exercises(tmp_path):
    repo = project(tmp_path, ["ex00/Makefile", "ex00/main.cpp"])
    exercise = files_rule(["Makefile", "*.cpp"], unit="ex01", pdf="cpp00.pdf")
    rules = [exercise, Rule(id="b", kind="build_unit", title="ex01: compiles", unit="ex01", sources=[Source(pdf="cpp00.pdf", page=5)])]
    assert check(repo, exercise, rules).status == "fail"                                    # an exercise is its own work, not shared code
    strict = [r.model_copy(update={"sources": [Source(pdf="libft.pdf", page=1)]}) for r in philo_rules()]
    philo = project(tmp_path / "p", ["philo/Makefile", "philo/philo.h", "philo/main.c"])
    assert check(philo, strict[2], strict).status == "fail"
