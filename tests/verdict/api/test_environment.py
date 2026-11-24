"""The environment check (sandbox + claude's terminal) and the health of the app."""

import pytest

from tests.verdict.api.support import UpSandbox, tools
from verdict.gateways.sandbox import SandboxError
from verdict.gateways.terminal import NullTerminal
from verdict.health import environment as environment_module


@pytest.fixture
def sandbox_selftest(monkeypatch):
    """The self-test the sandbox would run, scripted: `calls["sandbox"]` counts runs, `calls["deep"]` how it was asked."""
    calls = {"sandbox": 0, "deep": [], "tools": tools(), "error": None}

    def fake(sandbox, workspace, deep=False):
        calls["sandbox"] += 1
        calls["deep"].append(deep)
        if calls["error"]:
            raise calls["error"]
        return calls["tools"]

    monkeypatch.setattr(environment_module, "sandbox_selftest", fake)
    return calls


def test_environment_is_ready_when_both_containers_can_build_and_use_docker(make_client, sandbox_selftest):
    c, _ = make_client(sandbox=UpSandbox())
    env = c.get("/api/environment").json()
    assert env["ready"] is True and env["deep"] is False
    for part in ("sandbox", "terminal"):
        assert env[part]["available"] and env[part]["summary"]["ready"] and len(env[part]["tools"]) == 6


def test_a_missing_tool_in_either_container_makes_it_not_ready_and_says_which(make_client, terminal, sandbox_selftest):
    terminal.tools = tools(**{"C++ compiler (c++)": 1})
    c, _ = make_client(sandbox=UpSandbox())
    env = c.get("/api/environment").json()
    assert env["ready"] is False and env["sandbox"]["summary"]["ready"] is True
    assert env["terminal"]["summary"]["failed"] == ["C++ compiler (c++)"] and env["terminal"]["summary"]["basics_ok"] is False


def test_docker_without_a_daemon_is_reported_separately_from_the_basics(make_client, sandbox_selftest):
    sandbox_selftest["tools"] = tools(**{"docker daemon": 1})
    c, _ = make_client(sandbox=UpSandbox())
    env = c.get("/api/environment").json()
    assert env["ready"] is False
    assert env["sandbox"]["summary"]["basics_ok"] is True and env["sandbox"]["summary"]["docker_daemon_down"] is True


def test_an_unreachable_terminal_is_explained(make_client, terminal, sandbox_selftest):
    terminal.down = True
    c, _ = make_client(sandbox=UpSandbox())
    env = c.get("/api/environment").json()
    assert env["ready"] is False and env["sandbox"]["available"] is True
    assert env["terminal"]["available"] is False and "could not reach the terminal service" in env["terminal"]["error"]
    assert env["terminal"]["tools"] == []


def test_a_missing_sandbox_and_a_missing_terminal_are_explained(make_client, sandbox_selftest):
    c, _ = make_client(sandbox=None, terminal=NullTerminal())
    env = c.get("/api/environment").json()
    assert env["ready"] is False and "not configured" in env["sandbox"]["error"] and "not configured" in env["terminal"]["error"]
    assert sandbox_selftest["sandbox"] == 0                                      # (no sandbox: nothing was run)


@pytest.mark.parametrize("error", [SandboxError("sandbox unreachable: refused"), OSError("no route")])
def test_a_sandbox_that_cannot_be_reached_is_explained_not_raised(make_client, sandbox_selftest, error):
    sandbox_selftest["error"] = error
    c, _ = make_client(sandbox=UpSandbox())
    env = c.get("/api/environment")
    assert env.status_code == 200 and env.json()["sandbox"]["available"] is False and str(error) in env.json()["sandbox"]["error"]
    assert env.json()["terminal"]["available"] is True and env.json()["ready"] is False


def test_the_check_is_cached_briefly_and_deep_is_passed_through(make_client, terminal, sandbox_selftest):
    c, _ = make_client(sandbox=UpSandbox())
    c.get("/api/environment")
    c.get("/api/environment")
    assert sandbox_selftest["sandbox"] == 1 and len(terminal.of("environment")) == 1      # the second call is served from the cache
    c.get("/api/environment", params={"deep": "true"})
    assert sandbox_selftest["sandbox"] == 2 and sandbox_selftest["deep"] == [False, True]         # a deep test is never answered from the shallow cache
    assert terminal.of("environment") == [("environment", False), ("environment", True)]
    assert c.get("/api/environment", params={"deep": "true"}).json()["deep"] is True and sandbox_selftest["sandbox"] == 2


def test_the_cache_does_not_outlive_its_time(make_client, sandbox_selftest, monkeypatch):
    c, _ = make_client(sandbox=UpSandbox())
    c.get("/api/environment")
    monkeypatch.setattr(environment_module, "CACHE_SECONDS", 0)
    c.get("/api/environment")
    assert sandbox_selftest["sandbox"] == 2


def test_the_health_says_whether_the_sandbox_is_up(make_client):
    c, _ = make_client(sandbox=None)
    health = c.get("/api/health").json()
    assert health["status"] == "ok" and health["sandbox"] is False
    up, _ = make_client(sandbox=UpSandbox())
    assert up.get("/api/health").json()["sandbox"] is True

    class Down:
        def healthy(self):
            return False

    down, _ = make_client(sandbox=Down())
    assert down.get("/api/health").json()["sandbox"] is False


def test_the_health_says_which_ai_is_configured(client, monkeypatch):
    c, _ = client
    assert c.get("/api/health").json()["llm"] == {"configured": False, "model": "claude-opus-5-5", "provider": "anthropic", "host": "api.anthropic.com"}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert c.get("/api/health").json()["llm"]["configured"] is True
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "llama")
    assert c.get("/api/health").json()["llm"] == {"configured": True, "model": "llama", "provider": "openai", "host": "localhost"}

