"""src/terminal/editor/cli.py: `python -m editor_launcher`: what it starts, and what it wires."""

import pytest
from fastapi.testclient import TestClient

from terminal.editor import cli
from tests.terminal.fakes import HEADERS, environment_of


def test_without_arguments_it_runs_the_service_next_to_the_editor(world, monkeypatch, capsys):
    served = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: served.update(app=app, **kwargs))
    cli.main([], environment_of(world.tmp))
    assert served["host"] == "0.0.0.0" and served["port"] == 8002
    assert "is missing; only the terminal service runs" in capsys.readouterr().err
    client = TestClient(served["app"])
    assert client.get("/health").json()["status"] == "ok" and client.get("/sessions/sess-abc123/report", headers=HEADERS).json()["found"] is False


def test_the_editor_is_started_with_the_service_and_stopped_when_it_ends(world, monkeypatch):
    server = world.settings.editor.server
    server.write_text("#!/bin/sh\nexec sleep 60\n")
    server.chmod(0o755)
    started = []
    real_start = cli.EditorServer.start
    monkeypatch.setattr(cli.EditorServer, "start", lambda self: started.append(real_start(self)) or started[-1])
    monkeypatch.setattr(cli.EditorServer, "_token_file", lambda self: None)         # (the token file is /tmp/editor-token: not for a test)
    running = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: running.append(started[0].poll() is None))
    cli.main([], environment_of(world.tmp))
    assert running == [True], "the editor was up while the service ran"
    started[0].wait(timeout=10)                                                      # the service ended: the editor's group got SIGTERM
    assert started[0].returncode is not None


def test_claude_is_wired_from_the_environment_and_started_with_the_arguments(world, monkeypatch):
    calls = []

    class Recorder:
        def __init__(self, projects, folders, reports, environment, command):
            calls.append((projects.root, folders, command.executable, environment.settings.token))

        def start(self, session, project, prompt_file):
            calls.append((session, project, prompt_file))

    monkeypatch.setattr(cli, "ClaudeLauncher", Recorder)
    cli.main(["claude", "--session", "abcdef123", "--project", "/projects/x", "--prompt-file", "/tmp/p"], environment_of(world.tmp))
    assert calls == [(world.projects, world.settings.folders, str(world.stub), "t0ken-for-tests"), ("abcdef123", "/projects/x", "/tmp/p")]


def test_claude_needs_a_session_and_a_project(world):
    for args in (["claude"], ["claude", "--session", "abcdef123"], ["claude", "--project", "/projects/x"]):
        with pytest.raises(SystemExit):
            cli.main(args, environment_of(world.tmp))
