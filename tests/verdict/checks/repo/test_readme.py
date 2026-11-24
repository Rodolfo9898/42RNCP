"""The README the common-core subjects dictate."""

from verdict.checks.repo.readme import ReadmeChecker
from verdict.core.models import Rule

from tests.verdict.checks.helpers import answer, project

FIRST = "*This project has been created as part of the 42 curriculum by rperez-t*\n"
SECTIONS = "\n## Description\nx\n## Instructions\nx\n## Resources\n"


def readme(tmp_path, files):
    rule = Rule(id="r", kind="readme", title="README.md meets the subject's requirements", params={"sections": ["Description", "Instructions", "Resources"]})
    return answer(ReadmeChecker(), project(tmp_path, files), rule)


def test_a_complete_readme_passes(tmp_path):
    r = readme(tmp_path, {"README.md": FIRST + SECTIONS + "Documentation. AI explained complexity classes.\n"})
    assert r.status == "pass" and "required first line and sections" in r.detail


def test_no_readme_or_one_with_another_name_fails(tmp_path):
    none = readme(tmp_path / "a", ["main.c"])
    assert none.status == "fail" and "No README.md found at the root" in none.detail
    lower = readme(tmp_path / "b", ["readme.md"])
    assert lower.status == "fail" and "Found `readme.md`, but the subject requires a file named exactly README.md" in lower.detail


def test_the_first_line_and_the_sections_are_checked(tmp_path):
    r = readme(tmp_path, {"README.md": "# push_swap\n\n## Description\nx\n"})
    assert r.status == "fail" and "the very first line must be italicized" in r.detail
    assert "missing a “Instructions” section" in r.detail and "missing a “Resources” section" in r.detail
    assert r.evidence[0].file == "README.md" and r.evidence[0].snippet == "# push_swap"


def test_the_login_placeholder_is_refused(tmp_path):
    r = readme(tmp_path, {"README.md": "*This project has been created as part of the 42 curriculum by <login>*\n" + SECTIONS})
    assert r.status == "fail" and "still contains the <login> placeholder" in r.detail


def test_resources_that_say_nothing_about_ai_are_a_second_look(tmp_path):
    r = readme(tmp_path, {"README.md": FIRST + SECTIONS + "Some books.\n"})
    assert r.status == "warn" and "does not say how AI was used" in r.detail and r.evidence[0].line == 7
