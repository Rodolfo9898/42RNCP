"""Progress.md through the API: the result the verdict shows now is recorded in the row of its project, once you accept it."""

import pytest

from tests.verdict.api.support import made_session, new_session
from verdict.core.models import CheckResult
from verdict.sessions.store import RepoMeta

TABLE = """# Projects

Which projects were run.

| Project | Run |
|---|:---:|
| born2beroot | ⬜ |
| libft | ⬜ |
| push_swap | ✅ |

✅ run and accepted · ⬜ not run
"""


def record(c, sid):
    return c.put(f"/api/sessions/{sid}/progress")


@pytest.fixture
def progress_client(make_client, tmp_path):
    file = tmp_path / "Progress.md"
    file.write_text(TABLE)
    c, harness = make_client(progress_file=file)
    return c, harness, file


def test_the_result_the_verdict_shows_is_recorded_in_the_project_row(progress_client):
    c, harness, file = progress_client
    sid, session = made_session(c, harness)
    done = record(c, sid)
    assert done.status_code == 200
    assert done.json() == {"project": "libft", "result": "PASS", "symbol": "✅", "before": "⬜", "changed": True}
    assert file.read_text() == TABLE.replace("| libft | ⬜ |", "| libft | ✅ |")
    assert record(c, sid).json()["changed"] is False
    session.results.append(CheckResult(rule_id="r2", title="A check by hand", status="manual", section="mandatory"))
    assert record(c, sid).json()["symbol"] == "⚠️"                 # follows the verdict as it is now
    session.results[0] = CheckResult(rule_id="r1", title="A check", status="fail", section="mandatory")
    assert record(c, sid).json()["symbol"] == "❌"
    assert "| libft | ❌ |" in file.read_text() and file.read_text().count("libft") == 1


def test_the_file_is_written_in_place_so_the_host_keeps_seeing_it(progress_client, tmp_path):
    c, harness, file = progress_client
    inode = file.stat().st_ino
    sid, _ = made_session(c, harness)
    record(c, sid)
    assert file.stat().st_ino == inode and not list(tmp_path.glob("*.new")) and not list(tmp_path.glob("*.tmp"))


def test_nothing_is_recorded_without_a_file(client):
    c, harness = client
    sid, _ = made_session(c, harness)
    off = record(c, sid)
    assert off.status_code == 404 and "make run" in off.json()["detail"]


def test_nothing_is_recorded_without_a_result(progress_client):
    c, harness, file = progress_client
    sid = new_session(c)
    assert record(c, sid).status_code == 400                           # no project, no checks
    sid2, session = made_session(c, harness)
    session.results = []
    refused = record(c, sid2)
    assert refused.status_code == 400 and "run the checks first" in refused.json()["detail"]
    assert file.read_text() == TABLE
    assert record(c, "nope").status_code == 404


def test_an_unwritable_file_is_explained(make_client, tmp_path):
    folder = tmp_path / "Progress.md"
    folder.mkdir()                                                     # what Docker makes when the file did not exist
    c, harness = make_client(progress_file=folder)
    sid, _ = made_session(c, harness)
    bad = record(c, sid)
    assert bad.status_code == 503 and "cannot be written" in bad.json()["detail"]


def test_an_empty_file_made_by_make_gets_its_table(make_client, tmp_path):
    file = tmp_path / "Progress.md"
    file.write_text("")
    c, harness = make_client(progress_file=file)
    sid, _ = made_session(c, harness, name="scop")
    record(c, sid)
    assert "| scop | ✅ |" in file.read_text() and file.read_text().startswith("# Projects")


def test_a_file_that_does_not_exist_yet_is_created_with_its_table(make_client, tmp_path):
    file = tmp_path / "Progress.md"
    c, harness = make_client(progress_file=file)
    sid, _ = made_session(c, harness, name="scop")
    assert record(c, sid).json()["before"] is None and "| scop | ✅ |" in file.read_text()


def test_a_project_name_that_could_break_the_table_is_refused_and_the_file_is_left_alone(progress_client):
    c, harness, file = progress_client
    sid, _ = made_session(c, harness, name="a|b")
    assert record(c, sid).status_code == 400 and file.read_text() == TABLE


def test_a_folder_without_a_name_is_recorded_under_its_folder_name(progress_client):
    c, harness, file = progress_client
    sid, session = made_session(c, harness)
    session.repo = RepoMeta(url="", commit="", name="", path="42/libft")
    assert record(c, sid).json()["project"] == "libft" and "| libft | ✅ |" in file.read_text()
