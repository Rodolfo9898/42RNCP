"""src/terminal/editor/server.py: the editor, started with claude's environment and nothing of the service's secrets."""

import json
import stat
from dataclasses import replace

from terminal.editor.server import EditorServer
from terminal.environment.child import ChildEnvironment
from terminal.settings.settings import Settings
from tests.terminal.fakes import FakeDisplay, environment_of

RECORD_ARGV = """#!/bin/sh
echo "$@" > "%(log)s"
"""


def server_for(world, display, **kwargs):
    return EditorServer(world.settings.editor, world.settings.folders.reports_root, ChildEnvironment(world.settings, display), **kwargs)


def test_the_editor_and_its_terminals_get_no_secret_of_the_service(world, display, monkeypatch):
    monkeypatch.setenv("TERMINAL_TOKEN", "secret-terminal")                          # (in this process's own environment too)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-key")
    env = server_for(world, display).environment()
    assert not {"TERMINAL_TOKEN", "EDITOR_TOKEN", "ANTHROPIC_API_KEY", "LLM_API_KEY"} & env.keys()
    assert "secret-terminal" not in env.values() and "editor-secret" not in env.values() and "sk-must-not-leak" not in env.values()
    assert env["VERDICT_API"] == "http://web:8000" and env["GIT_CONFIG_VALUE_0"] == "*" and env["SHELL"] == "/bin/bash"
    assert env["REPORTS_ROOT"] == str(world.reports), "where the Verdict extension looks for claude's report"


def test_the_editor_gets_the_display_and_the_zsh_config_when_there_are_some(world, display):
    settings = Settings.from_environment(environment_of(world.tmp, ZDOTDIR="/etc/verdict-zsh", TERMINAL_SHELL="/usr/bin/zsh"))
    env = EditorServer(settings.editor, world.reports, ChildEnvironment(settings, FakeDisplay({"DISPLAY": ":99"}))).environment()
    assert (env["SHELL"], env["ZDOTDIR"], env["DISPLAY"]) == ("/usr/bin/zsh", "/etc/verdict-zsh", ":99")
    assert "ZDOTDIR" not in server_for(world, display).environment()


def test_the_editor_is_only_there_when_its_executable_is(world, display):
    assert server_for(world, display).available() is False
    world.settings.editor.server.write_text("#!/bin/sh\n")
    assert server_for(world, display).available() is True


def test_the_default_settings_are_the_machine_level_ones(world, display):
    editor = world.settings.editor
    editor.default_settings.write_text(json.dumps({"editor.fontSize": 14}))
    server_for(world, display).write_default_settings()
    assert json.loads((editor.data / "data" / "Machine" / "settings.json").read_text()) == {"editor.fontSize": 14}


def test_missing_default_settings_are_reported_and_do_not_stop_the_editor(world, display, capsys):
    server_for(world, display).write_default_settings()
    assert "default settings not written" in capsys.readouterr().err


def started_with(world, display, tmp_path, **env):
    log = tmp_path / "argv"
    exe = world.settings.editor.server
    exe.write_text(RECORD_ARGV % {"log": log})
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    editor = replace(world.settings.editor, **env)
    token_path = tmp_path / "editor-token"
    process = EditorServer(editor, world.reports, ChildEnvironment(world.settings, display), token_path=token_path).start()
    process.wait(timeout=10)
    return log.read_text().split(), token_path


def test_the_editor_starts_behind_a_connection_token_kept_in_a_file_only_its_user_reads(world, display, tmp_path):
    argv, token_path = started_with(world, display, tmp_path)
    editor = world.settings.editor
    assert argv == ["--host", "0.0.0.0", "--port", "3000", "--server-data-dir", str(editor.data), "--extensions-dir", str(editor.extensions),
                    "--default-folder", editor.folder, "--telemetry-level", "off", "--connection-token-file", str(token_path)]
    assert token_path.read_text() == "editor-secret" and stat.S_IMODE(token_path.stat().st_mode) == 0o600
    assert "editor-secret" not in " ".join(argv), "the token is never on a command line"


def test_without_a_token_the_editor_says_so_and_no_file_is_written(world, display, tmp_path):
    argv, token_path = started_with(world, display, tmp_path, token="")
    assert argv[-1] == "--without-connection-token" and "--connection-token-file" not in argv and not token_path.exists()
