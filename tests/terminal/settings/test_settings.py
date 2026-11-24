"""src/terminal/settings: what the service reads from its environment, once."""

from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from terminal.settings.folders import SessionFolders
from terminal.settings.limits import Limits
from terminal.settings.settings import Settings
from tests.terminal.fakes import environment_of


def test_without_any_variable_the_container_defaults_apply():
    settings = Settings.from_environment({})
    assert (settings.projects, settings.scratch, settings.claude, settings.home) == (Path("/projects"), Path("/scratch"), "claude", "/home/term")
    assert settings.token == "" and settings.claude_config_dir == "/home/term/.claude" and settings.docker_host == settings.ssh_auth_sock == ""
    assert settings.folders == SessionFolders(Path("/scratch/subjects"), Path("/scratch/reports"))
    assert settings.limits == Limits() and settings.ssh_agent_ready is False


def test_the_variables_of_the_container_are_read(tmp_path):
    env = environment_of(tmp_path, CLAUDE_CONFIG_DIR="/c", DOCKER_HOST="tcp://dind:2375", SSH_AUTH_SOCK="/s.sock", TERMINAL_HOME="/h")
    settings = Settings.from_environment(env)
    assert settings.projects == tmp_path / "projects" and settings.scratch == tmp_path / "scratch" and settings.token == "t0ken-for-tests"
    assert settings.claude == str(tmp_path / "claude-stub") and settings.home == "/h" and settings.claude_config_dir == "/c"
    assert settings.folders == SessionFolders(tmp_path / "subjects", tmp_path / "reports")
    assert (settings.docker_host, settings.ssh_auth_sock) == ("tcp://dind:2375", "/s.sock")
    assert settings.editor.token == "editor-secret" and settings.editor.data == tmp_path / "editor-data"


def test_the_settings_are_made_once_and_not_changed(tmp_path):
    settings = Settings.from_environment(environment_of(tmp_path))
    with pytest.raises(FrozenInstanceError):
        settings.token = "other"
    with pytest.raises(FrozenInstanceError):
        settings.limits.max_subject_files = 1
    assert "workdir" not in {f.name for f in fields(Settings)}, "claude always works in the project folder"


def test_a_session_folder_exists_only_for_a_session_id(tmp_path):
    folders = SessionFolders(tmp_path / "subjects", tmp_path / "reports")
    assert folders.subjects("sess-abc123") == tmp_path / "subjects" / "sess-abc123"
    assert folders.reports("sess-abc123") == tmp_path / "reports" / "sess-abc123"
    for bad in ("", "short", "../../etc", "a/b", "x" * 33, "with space", "dot.dot.dot"):
        assert not folders.is_valid(bad) and folders.subjects(bad) is None and folders.reports(bad) is None, bad
    assert folders.is_valid("a" * 6) and folders.is_valid("A_b-9" + "z" * 27)


def test_the_editor_settings_follow_the_home_folder_unless_told_otherwise(tmp_path):
    editor = Settings.from_environment({"TERMINAL_HOME": "/home/x"}).editor
    assert editor.data == Path("/home/x/.openvscode-server") and editor.extensions == Path("/home/x/.openvscode-server/extensions")
    assert editor.extensions_list == Path("/config/extensions.txt") and editor.port == "3000" and editor.folder == "/projects"
    assert editor.verdict_api == "http://web:8000" and editor.shell == "/bin/bash" and editor.zdotdir == "" and editor.token == ""
    assert Settings.from_environment({"EDITOR_TOKEN": "  spaced \n"}).editor.token == "spaced"
