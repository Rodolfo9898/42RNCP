"""Progress.md: the table of which projects were run, updated from the editor once the result is one you accept."""

import re
from pathlib import Path

import pytest

from verdict import progress

from .test_api import client  # noqa: F401  (the same app, workspace and library as the API tests)

ROOT = Path(__file__).resolve().parent.parent
TABLE = """# Projects

Which projects were run.

| Project | Run |
|---|:---:|
| born2beroot | ⬜ |
| libft | ⬜ |
| push_swap | ✅ |

✅ run and accepted · ⬜ not run
"""


def test_a_result_has_a_symbol_and_nothing_else_does():
    assert [progress.symbol_for(r) for r in ("PASS", "PASS WITH ISSUES", "FAIL")] == ["✅", "⚠️", "❌"]
    for nothing in ("NOT RUN", "", "pass"):
        with pytest.raises(progress.ProgressError, match="no result to record"):
            progress.symbol_for(nothing)


def test_only_the_row_of_the_project_changes():
    new, before = progress.update(TABLE, "libft", "⚠️")
    assert before == "⬜" and new == TABLE.replace("| libft | ⬜ |", "| libft | ⚠️ |")
    assert progress.update(new, "libft", "⚠️") == (new, "⚠️")                  # the same again: nothing changes
    assert progress.update(TABLE, "LIBFT", "❌")[0] == TABLE.replace("| libft | ⬜ |", "| libft | ❌ |")      # found whatever the case, name kept


def test_a_project_without_a_row_is_added_in_its_alphabetical_place():
    new, before = progress.update(TABLE, "cub3d", "✅")
    assert before is None
    rows = re.findall(r"^\| ([\w.-]+) \|", new, re.M)
    assert rows == ["Project", "born2beroot", "cub3d", "libft", "push_swap"]
    assert progress.update(TABLE, "zappy", "✅")[0].index("| zappy | ✅ |") > progress.update(TABLE, "zappy", "✅")[0].index("| push_swap |")
    assert progress.update(TABLE, "zappy", "✅")[0].endswith("\n✅ run and accepted · ⬜ not run\n")        # the legend stays below the table


def test_everything_around_the_table_is_kept_byte_for_byte():
    text = "intro the person wrote\r\n\n" + TABLE.split("\n\n", 1)[1] + "\nmy notes: |x|y|\n"
    new, _ = progress.update(text, "libft", "✅")
    assert new == text.replace("| libft | ⬜ |", "| libft | ✅ |")


def test_an_empty_or_table_less_file_gets_a_table():
    new, before = progress.update("", "libft", "✅")
    assert before is None and new.startswith("# Projects") and "| Project | Run |\n|---|:---:|\n| libft | ✅ |" in new and "run and accepted" in new
    again, _ = progress.update(new, "libft", "❌")
    assert again.count("| libft |") == 1 and "| libft | ❌ |" in again
    notes, _ = progress.update("just some notes\n", "libft", "✅")
    assert notes.startswith("just some notes\n") and "| libft | ✅ |" in notes


@pytest.mark.parametrize("name", ["", "a|b", "a b", "../x", "x\ny", "| ✅ |"])
def test_a_name_that_could_break_the_table_is_refused(name):
    with pytest.raises(progress.ProgressError):
        progress.update(TABLE, name, "✅")


# ---------------------------------------------------------------- the endpoint


def made_session(c, main, *, status="pass", name="libft"):
    sid = c.post("/api/sessions").json()["id"]
    session = main.store.get(sid)
    session.repo = main.RepoMeta(url="", commit="", name=name, path=name)
    session.results = [main.CheckResult(rule_id="r1", title="A check", status=status, section="mandatory")]
    return sid, session


def test_the_result_the_verdict_shows_is_recorded_in_the_project_row(client, tmp_path, monkeypatch):
    c, main = client
    file = tmp_path / "Progress.md"
    file.write_text(TABLE)
    monkeypatch.setattr(main, "PROGRESS_FILE", file)
    sid, session = made_session(c, main)
    done = c.post(f"/api/sessions/{sid}/progress").json()
    assert done == {"project": "libft", "result": "PASS", "symbol": "✅", "before": "⬜", "changed": True}
    assert file.read_text() == TABLE.replace("| libft | ⬜ |", "| libft | ✅ |")
    assert c.post(f"/api/sessions/{sid}/progress").json()["changed"] is False
    session.results.append(main.CheckResult(rule_id="r2", title="A check by hand", status="manual", section="mandatory"))
    assert c.post(f"/api/sessions/{sid}/progress").json()["symbol"] == "⚠️"                 # follows the verdict as it is now
    session.results[0] = main.CheckResult(rule_id="r1", title="A check", status="fail", section="mandatory")
    assert c.post(f"/api/sessions/{sid}/progress").json()["symbol"] == "❌"
    assert "| libft | ❌ |" in file.read_text() and file.read_text().count("libft") == 1


def test_the_file_is_written_in_place_so_the_host_keeps_seeing_it(client, tmp_path, monkeypatch):
    c, main = client
    file = tmp_path / "Progress.md"
    file.write_text(TABLE)
    inode = file.stat().st_ino
    monkeypatch.setattr(main, "PROGRESS_FILE", file)
    sid, _ = made_session(c, main)
    c.post(f"/api/sessions/{sid}/progress")
    assert file.stat().st_ino == inode and not list(tmp_path.glob("*.new")) and not list(tmp_path.glob("*.tmp"))


def test_nothing_is_recorded_without_a_result_or_a_file(client, tmp_path, monkeypatch):
    c, main = client
    sid = c.post("/api/sessions").json()["id"]
    monkeypatch.setattr(main, "PROGRESS_FILE", None)
    off = c.post(f"/api/sessions/{sid}/progress")
    assert off.status_code == 404 and "make run" in off.json()["detail"]
    file = tmp_path / "Progress.md"
    file.write_text(TABLE)
    monkeypatch.setattr(main, "PROGRESS_FILE", file)
    assert c.post(f"/api/sessions/{sid}/progress").status_code == 400                           # no project, no checks
    sid2, session = made_session(c, main)
    session.results = []
    assert c.post(f"/api/sessions/{sid2}/progress").status_code == 400
    assert file.read_text() == TABLE
    assert c.post("/api/sessions/nope/progress").status_code == 404


def test_an_unwritable_file_is_explained(client, tmp_path, monkeypatch):
    c, main = client
    folder = tmp_path / "Progress.md"
    folder.mkdir()                                                                              # what Docker makes when the file did not exist
    monkeypatch.setattr(main, "PROGRESS_FILE", folder)
    sid, _ = made_session(c, main)
    bad = c.post(f"/api/sessions/{sid}/progress")
    assert bad.status_code == 503 and "cannot be written" in bad.json()["detail"]


def test_an_empty_file_made_by_make_gets_its_table(client, tmp_path, monkeypatch):
    c, main = client
    file = tmp_path / "Progress.md"
    file.write_text("")
    monkeypatch.setattr(main, "PROGRESS_FILE", file)
    sid, _ = made_session(c, main, name="scop")
    c.post(f"/api/sessions/{sid}/progress")
    assert "| scop | ✅ |" in file.read_text() and file.read_text().startswith("# Projects")


# ---------------------------------------------------------------- how it is wired


def test_only_the_web_app_sees_progress_md_and_make_creates_it_first():
    compose = (ROOT / "docker-compose.yml").read_text()
    services = re.split(r"\n  (?=[a-z]+:\n)", compose)
    seeing = [s.split(":", 1)[0].strip() for s in services if "Progress.md" in s and not s.startswith("#")]
    assert seeing == ["web"] or [x for x in seeing if x.startswith("web")]
    assert "PROGRESS_FILE: /progress/Progress.md" in compose and "- ./Progress.md:/progress/Progress.md" in compose
    makefile = (ROOT / "Makefile").read_text()
    assert re.search(r"^build:.*\bprogress\b", makefile, re.M) and "[ -e Progress.md ] || : > Progress.md" in makefile


def test_the_editor_command_and_its_button_exist():
    import json
    ext = ROOT / "terminal" / "vscode" / "verdict"
    manifest = json.loads((ext / "package.json").read_text())
    assert "verdict.updateProgress" in {c["command"] for c in manifest["contributes"]["commands"]}
    assert any(m["command"] == "verdict.updateProgress" for m in manifest["contributes"]["menus"]["view/title"])
    assert 'command("verdict.updateProgress", updateProgress)' in (ext / "extension.js").read_text()
