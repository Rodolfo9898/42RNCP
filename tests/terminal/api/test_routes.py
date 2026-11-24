"""src/terminal/api: the internal REST API the web app's TerminalGateway talks to."""

import shutil
import stat
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from terminal.api.app import create_app
from terminal.report.files import ReportFiles
from terminal.settings.limits import Limits
from tests.terminal.fakes import HEADERS, TOKEN

GUARDED = [
    ("GET", "/sessions/sess-abc123/report"), ("DELETE", "/sessions/sess-abc123/report"),
    ("GET", "/sessions/sess-abc123/subjects"), ("PUT", "/sessions/sess-abc123/subjects"),
    ("GET", "/environment"), ("POST", "/reviews"),
]


# ---------------------------------------------------------------- the token: one check for every route but /health


@pytest.mark.parametrize("method,path", GUARDED)
def test_every_route_but_health_needs_the_token(client, method, path):
    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers={"x-terminal-token": "wrong"}).status_code == 401
    assert client.request(method, path, headers={"x-terminal-token": TOKEN + "x"}).status_code == 401
    assert client.request(method, path, headers={"x-terminal-token": "tökén".encode("latin-1")}).status_code == 401          # (not ASCII: refused, not a crash)
    assert client.request(method, path, headers=HEADERS).status_code != 401


@pytest.mark.parametrize("method,path", GUARDED)
def test_without_a_configured_token_everything_is_refused(world, display, method, path):
    client = TestClient(create_app(replace(world.settings, token=""), display))
    assert client.request(method, path, headers={"x-terminal-token": ""}).status_code == 401
    assert client.request(method, path).status_code == 401
    assert client.get("/health").status_code == 200


def test_a_refusal_says_so_and_does_nothing(world, client):
    answer = client.delete("/sessions/sess-abc123/report")
    assert answer.status_code == 401 and answer.json() == {"detail": "bad token"}


def test_the_old_routes_and_the_generated_docs_are_gone(client):
    for method, path in (("GET", "/result"), ("GET", "/selftest"), ("POST", "/prompts"), ("POST", "/review"), ("GET", "/subjects"),
                         ("POST", "/subjects"), ("GET", "/shells"), ("POST", "/pty/end"), ("GET", "/pty"), ("GET", "/docs"),
                         ("GET", "/redoc"), ("GET", "/openapi.json")):
        assert client.request(method, path, headers=HEADERS).status_code == 404, (method, path)


def test_the_virtual_display_is_stopped_with_the_service(world, display):
    with TestClient(create_app(world.settings, display)):
        assert display.stopped is False
    assert display.stopped is True


# ---------------------------------------------------------------- /health


def test_health_needs_no_token_and_says_whether_claude_is_installed(world, display):
    assert TestClient(create_app(world.settings, display)).get("/health").json() == {"status": "ok", "claude": True, "ssh": False}
    missing = replace(world.settings, claude="definitely-not-installed")
    assert TestClient(create_app(missing, display)).get("/health").json()["claude"] is False
    assert shutil.which(str(world.stub)) is not None


def test_health_says_whether_the_terminal_was_given_the_ssh_agent(world, display, tmp_path):
    def ssh(sock):
        return TestClient(create_app(replace(world.settings, ssh_auth_sock=sock), display)).get("/health").json()["ssh"]

    assert ssh("") is False                                                                    # the default: no agent, git cannot sign in
    assert ssh(str(tmp_path / "no-such.sock")) is False                                        # asked for, but the socket is not there
    sock = tmp_path / "agent.sock"
    sock.write_text("")                                                                        # (any file stands in for the socket)
    assert ssh(str(sock)) is True


# ---------------------------------------------------------------- the report


def test_the_report_is_read_and_deleted_through_the_api(world, client):
    report = ReportFiles(world.settings.folders).prepare("sess-abc123") / "claude-review.md"
    assert client.get("/sessions/sess-abc123/report", headers=HEADERS).json() == {"found": False, "text": "", "name": "claude-review.md"}
    report.write_text("# Report\n\n## Verdict\nready to pass\n")
    got = client.get("/sessions/sess-abc123/report", headers=HEADERS).json()
    assert got["found"] and "ready to pass" in got["text"] and got["name"] == "claude-review.md"
    assert client.get("/sessions/another-session/report", headers=HEADERS).json()["found"] is False
    assert client.delete("/sessions/sess-abc123/report", headers=HEADERS).json() == {"deleted": True}
    assert not report.exists() and client.get("/sessions/sess-abc123/report", headers=HEADERS).json()["found"] is False
    assert client.delete("/sessions/sess-abc123/report", headers=HEADERS).json() == {"deleted": False}


def test_a_link_or_a_huge_report_is_not_returned_through_the_api(world, display):
    report = ReportFiles(world.settings.folders).prepare("sess-liv008") / "claude-review.md"
    report.symlink_to(world.secret)
    client = TestClient(create_app(world.settings, display))
    assert client.get("/sessions/sess-liv008/report", headers=HEADERS).json()["found"] is False
    report.unlink()
    report.write_text("far too long for the limit")
    small = TestClient(create_app(replace(world.settings, limits=Limits(max_review_bytes=5)), display))
    assert small.get("/sessions/sess-liv008/report", headers=HEADERS).json()["found"] is False


def test_a_report_for_something_that_is_not_a_session_is_nothing(client):
    for sid in ("abc", "x" * 40, "a.b.c.d.e"):
        assert client.get(f"/sessions/{sid}/report", headers=HEADERS).json()["found"] is False
        assert client.delete(f"/sessions/{sid}/report", headers=HEADERS).json() == {"deleted": False}


# ---------------------------------------------------------------- the environment self-test


@pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc") and shutil.which("c++")), reason="needs make, cc and c++")
def test_the_environment_really_builds_and_runs_inside_the_terminals_environment(world, client):
    got = client.get("/environment", headers=HEADERS).json()["tools"]
    named = {t["name"]: t for t in got}
    assert named["claude"]["ok"] and named["claude"]["required"]            # the stub claude answers --version
    assert named["gdb"]["required"] is False                                # an extra, only in this container
    for step in ("C compiler (cc)", "C++ compiler (c++)", "make", "build C and C++ with make", "run the C program", "run the C++ program"):
        assert named[step]["ok"], named[step]
    assert list(world.scratch.iterdir()) == []                               # the scratch build is cleaned up


# ---------------------------------------------------------------- the one-click review


def post_review(client, headers=HEADERS, **body):
    payload = {"repo": "42/ps", "prompt": "Look at the code.", "schema": {"type": "object"}, **body}
    return client.post("/reviews", json=payload, headers=headers)


def test_review_runs_headless_claude_on_a_copy_and_cleans_up(world, client):
    r = post_review(client)
    assert r.status_code == 200
    data = r.json()
    assert data["returncode"] == 0 and '"result": "reviewed"' in data["stdout"]
    assert "--tools Read,Grep,Glob" in data["stdout"] and "--permission-mode dontAsk" in data["stdout"]
    assert list(world.scratch.iterdir()) == []


def test_review_needs_a_valid_repository_and_a_complete_request(client):
    assert post_review(client, repo="../outside").status_code == 400
    assert post_review(client, repo="missing").status_code == 400
    assert client.post("/reviews", json={"repo": "42/ps"}, headers=HEADERS).status_code == 400
    assert client.post("/reviews", content=b"not json", headers=HEADERS).status_code == 400
    assert client.post("/reviews", json=["a list"], headers=HEADERS).status_code == 400


def test_review_times_out(world, client):
    world.stub.write_text("#!/bin/sh\nsleep 30\n")
    world.stub.chmod(world.stub.stat().st_mode | stat.S_IEXEC)
    start = time.monotonic()
    r = post_review(client, timeout=1)
    assert r.status_code == 504 and time.monotonic() - start < 10
    assert list(world.scratch.iterdir()) == []
