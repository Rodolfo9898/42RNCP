import subprocess
from pathlib import Path

import pytest

from verdict.repository.repo.git.client import GitClient


def recorder(calls):
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, "out", "")
    return run


def test_the_networked_environment_is_built_from_nothing_of_ours(tmp_path, monkeypatch):
    monkeypatch.setenv("SSH_AUTH_SOCK", "/run/agent.sock")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    env = GitClient.networked(tmp_path / "ws" / "known_hosts").env
    assert set(env) == {"PATH", "HOME", "GIT_TERMINAL_PROMPT", "GIT_CONFIG_NOSYSTEM", "GIT_LFS_SKIP_SMUDGE", "GIT_SSH_COMMAND", "SSH_AUTH_SOCK"}
    assert env["HOME"] == str(tmp_path / "ws") and env["GIT_TERMINAL_PROMPT"] == "0" and env["SSH_AUTH_SOCK"] == "/run/agent.sock"
    assert "BatchMode=yes" in env["GIT_SSH_COMMAND"] and f"UserKnownHostsFile={tmp_path / 'ws' / 'known_hosts'}" in env["GIT_SSH_COMMAND"]


def test_without_an_agent_there_is_no_socket_in_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    client = GitClient.networked(tmp_path / "known_hosts")
    assert "SSH_AUTH_SOCK" not in client.env and not client.has_agent


def test_the_global_configuration_and_the_protocols_can_be_pinned(tmp_path):
    env = GitClient.networked(tmp_path / "known_hosts", global_config=False, protocols=("https", "ssh")).env
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null" and env["GIT_ALLOW_PROTOCOL"] == "https:ssh"
    plain = GitClient.networked(tmp_path / "known_hosts").env
    assert "GIT_CONFIG_GLOBAL" not in plain and "GIT_ALLOW_PROTOCOL" not in plain


def test_the_offline_environment_cannot_reach_a_home_or_a_server(monkeypatch):
    monkeypatch.setenv("SSH_AUTH_SOCK", "/run/agent.sock")
    client = GitClient.offline()
    assert client.env["HOME"] == "/nonexistent" and "SSH_AUTH_SOCK" not in client.env and "GIT_SSH_COMMAND" not in client.env
    assert client.env["GIT_TERMINAL_PROMPT"] == "0" and client.env["GIT_CONFIG_NOSYSTEM"] == "1"


def test_a_command_on_a_folder_is_told_what_not_to_run_from_it(tmp_path):
    calls = []
    GitClient.offline(recorder(calls)).run("log", "-1", folder=tmp_path, config=["protocol.allow=never"], timeout=7)
    cmd, kwargs = calls[0]
    assert cmd[0] == "git" and cmd[-4:] == ["-C", str(tmp_path), "log", "-1"]
    settings = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-c"]
    assert {f"safe.directory={tmp_path}", "core.fsmonitor=false", "core.hooksPath=/dev/null", "protocol.allow=never"} <= set(settings)
    assert kwargs["timeout"] == 7 and kwargs["capture_output"] and kwargs["text"] and kwargs["check"] is False and "env" in kwargs


def test_a_command_outside_any_folder_only_has_the_settings_it_asks_for():
    client = GitClient({"PATH": "/usr/bin"})
    assert client.command(["clone", "--", "u", "d"], config=["core.hooksPath=/dev/null"]) == ["git", "-c", "core.hooksPath=/dev/null", "clone", "--", "u", "d"]
    assert client.command(["status"]) == ["git", "status"]


def test_a_timeout_is_left_to_the_caller(tmp_path):
    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    with pytest.raises(subprocess.TimeoutExpired):
        GitClient.offline(slow).run("status", folder=Path(tmp_path))
