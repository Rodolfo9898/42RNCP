"""src/verdict/editor.py: the list of the editor's extensions (config/extensions.txt) and claude started from the Verdict extension."""

import json
import subprocess
from pathlib import Path

import pytest

from verdict import editor


def manifest(folder: Path, *ids: str) -> None:
    """The extensions.json VS Code keeps in its extensions folder."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "extensions.json").write_text(json.dumps([{"identifier": {"id": i}, "version": "1.0.0", "relativeLocation": f"{i}-1.0.0"} for i in ids]))


def test_the_list_keeps_ids_only_in_order_once_and_in_lower_case(tmp_path):
    path = tmp_path / "extensions.txt"
    path.write_text("# my extensions\nmhutchie.git-graph\n\n  Oderwat.Indent-Rainbow  # the indents\nnot an id\nmhutchie.git-graph\n../evil\n")
    assert editor.read_list(path) == ["mhutchie.git-graph", "oderwat.indent-rainbow"]
    assert editor.read_list(tmp_path / "missing.txt") == []


def test_writing_the_list_keeps_its_comments_and_sorts_the_ids(tmp_path):
    path = tmp_path / "extensions.txt"
    path.write_text("# mine\n# two lines\nzz.last\n")
    editor.write_list(["b.two", "a.one", "a.one"], path)
    assert path.read_text() == "# mine\n# two lines\na.one\nb.two\n"
    fresh = tmp_path / "fresh.txt"
    editor.write_list(["a.one"], fresh)
    assert fresh.read_text() == editor.HEADER + "a.one\n"


def test_installed_reads_the_manifest_and_survives_a_broken_one(tmp_path):
    manifest(tmp_path, "mhutchie.git-graph", "Oderwat.indent-rainbow")
    assert editor.installed(tmp_path) == {"mhutchie.git-graph", "oderwat.indent-rainbow"}
    (tmp_path / "extensions.json").write_text("{not json")
    assert editor.installed(tmp_path) == set()
    assert editor.installed(tmp_path / "nothing") == set()


def test_an_extension_installed_in_the_editor_is_added_and_one_uninstalled_is_taken_off(tmp_path):
    path = tmp_path / "extensions.txt"
    editor.write_list(["mhutchie.git-graph", "never.installed"], path)
    assert editor.sync({"mhutchie.git-graph"}, {"mhutchie.git-graph", "new.one"}, path)
    assert editor.read_list(path) == ["mhutchie.git-graph", "never.installed", "new.one"]
    assert editor.sync({"mhutchie.git-graph", "new.one"}, {"new.one"}, path)
    assert editor.read_list(path) == ["never.installed", "new.one"], "an id whose install failed stays for the next start"
    assert not editor.sync({"new.one"}, {"new.one"}, path), "nothing changed: the file is not written"


def test_only_the_missing_extensions_are_installed_and_a_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "EXTENSIONS", tmp_path / "ext")
    monkeypatch.setattr(editor, "server_env", lambda: {})
    manifest(tmp_path / "ext", "mhutchie.git-graph")
    calls = []

    def run(argv, **_):
        calls.append(argv[-1])
        return subprocess.CompletedProcess(argv, 1 if argv[-1] == "offline.one" else 0, "", "network down")

    assert editor.install_missing(["mhutchie.git-graph", "new.one", "offline.one"], run=run) == ["offline.one"]
    assert calls == ["new.one", "offline.one"], "git-graph is already installed"


def test_the_editor_and_its_terminals_get_no_secret_of_the_service(monkeypatch):
    monkeypatch.setenv("TERMINAL_TOKEN", "secret-terminal")
    monkeypatch.setenv("EDITOR_TOKEN", "secret-editor")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-key")
    monkeypatch.setattr("verdict.terminal.display_env", lambda: {})
    env = editor.server_env()
    assert not {"TERMINAL_TOKEN", "EDITOR_TOKEN", "ANTHROPIC_API_KEY"} & env.keys()
    assert env["VERDICT_API"] == "http://web:8000" and env["GIT_CONFIG_VALUE_0"] == "*"


def test_claude_is_only_started_in_a_project_and_for_a_real_review(tmp_path, monkeypatch):
    monkeypatch.setattr("verdict.terminal.PROJECTS", tmp_path)
    with pytest.raises(SystemExit):
        editor.claude("abcdef123", "/etc", "")
    with pytest.raises(SystemExit):
        editor.claude("../../x", str(tmp_path), "")


def test_claude_starts_in_the_project_with_the_prompt_and_its_report_outside(tmp_path, monkeypatch):
    project = tmp_path / "projects" / "cub3d"
    project.mkdir(parents=True)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("review this")
    monkeypatch.setattr("verdict.terminal.PROJECTS", tmp_path / "projects")
    monkeypatch.setattr("verdict.terminal.REPORTS_ROOT", tmp_path / "reports")
    monkeypatch.setattr("verdict.terminal.display_env", lambda: {})
    started = {}
    monkeypatch.setattr(editor.os, "execvpe", lambda exe, argv, env: started.update(argv=argv, env=env, cwd=Path.cwd()))
    monkeypatch.chdir(tmp_path)
    editor.claude("abcdef123", str(project), str(prompt))
    assert started["argv"][-1] == "review this" and started["cwd"] == project
    assert started["env"]["REPORT_DIR"] == str(tmp_path / "reports" / "abcdef123") and Path(started["env"]["REPORT_DIR"]).is_dir()
    assert not prompt.exists(), "the prompt file is used once"
