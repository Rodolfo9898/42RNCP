import os
import socket
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

from verdict import repo

ENTRYPOINT = Path(__file__).resolve().parent.parent / "entrypoint.sh"


# ---------------------------------------------------------------- ssh_status


def fake_ssh_add(monkeypatch, rc, stdout="", stderr=""):
    monkeypatch.setattr(repo.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], rc, stdout, stderr))


def test_status_without_agent(monkeypatch):
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    status = repo.ssh_status()
    assert (status["ok"], status["code"]) == (False, "no-agent")


def test_status_with_missing_socket(monkeypatch, tmp_path):
    monkeypatch.setenv("SSH_AUTH_SOCK", str(tmp_path / "nope.sock"))
    assert repo.ssh_status()["code"] == "no-socket"


@pytest.fixture
def sock_file(monkeypatch, tmp_path):
    path = tmp_path / "agent.sock"
    path.write_text("")
    monkeypatch.setenv("SSH_AUTH_SOCK", str(path))
    return path


def test_status_ok_lists_keys(monkeypatch, sock_file):
    fake_ssh_add(monkeypatch, 0, stdout="256 SHA256:abc me@laptop (ED25519)\n3072 SHA256:def work (RSA)\n")
    status = repo.ssh_status()
    assert status["ok"] and len(status["keys"]) == 2 and "2 key" in status["message"]


def test_status_agent_without_keys(monkeypatch, sock_file):
    fake_ssh_add(monkeypatch, 1, stdout="The agent has no identities.\n")
    status = repo.ssh_status()
    assert (status["ok"], status["code"]) == (False, "no-keys") and "ssh-add" in status["message"]


def test_status_permission_denied(monkeypatch, sock_file):
    fake_ssh_add(monkeypatch, 2, stderr="Error connecting to agent: Permission denied\n")
    assert repo.ssh_status()["code"] == "permission"


def test_status_other_connection_error(monkeypatch, sock_file):
    fake_ssh_add(monkeypatch, 2, stderr="Could not open a connection to your authentication agent.\n")
    assert repo.ssh_status()["code"] == "unreachable"


# ---------------------------------------------------------------- clone errors


def test_clone_error_keeps_the_real_cause_and_adds_a_hint():
    stderr = ("Cloning into '/projects/x'...\n"
              "git@github.com: Permission denied (publickey).\n"
              "fatal: Could not read from remote repository.\n\n"
              "Please make sure you have the correct access rights\nand the repository exists.\n")
    message = repo.explain_clone_failure(stderr, 128)
    assert "Permission denied (publickey)" in message and "repository exists" in message
    assert "ssh-add" in message and "Cloning into" not in message


def test_clone_error_without_output():
    assert "exit code 255" in repo.explain_clone_failure("", 255)


def test_clone_error_host_key_hint():
    assert "known_hosts" in repo.explain_clone_failure("Host key verification failed.\n", 128)


# ---------------------------------------------------------------- entrypoint.sh


@pytest.fixture
def sandbox_dir():
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="ep") as d:  # short path: unix socket names are length-limited
        yield Path(d)


def stub(path: Path, body: str):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def run_entrypoint(root: Path, *, uid: str, socat: str | None, host_socket: bool = True, app_uid: str = "4242"):
    bin_dir = root / "bin"
    bin_dir.mkdir()
    stub(bin_dir / "id", f'echo {uid}\n')
    # setpriv stub: drop its three option arguments, report the agent socket, run the command
    stub(bin_dir / "setpriv", 'shift 3\necho "SETPRIV SSH=$SSH_AUTH_SOCK"\nexec "$@"\n')
    if socat:
        stub(bin_dir / "socat", socat)
    host = root / "host.sock"
    if host_socket:
        s = socket.socket(socket.AF_UNIX)
        try:
            s.bind(str(host))
        except PermissionError:
            pytest.skip("this environment forbids binding unix sockets")
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOST_SSH_SOCK": str(host), "PROXY_SSH_SOCK": str(root / "proxy.sock"),
           "SSH_AUTH_SOCK": str(host), "APP_UID": app_uid}       # 4242: a socket the app user does not own (Docker Desktop)
    proc = subprocess.run(["sh", str(ENTRYPOINT), "sh", "-c", 'echo "APP SSH=$SSH_AUTH_SOCK"'],
                          env=env, capture_output=True, text=True, timeout=30)
    return proc, host, root / "proxy.sock"


RELAY = """
python3 - "$1" >/dev/null 2>&1 <<'PY' &
import socket, sys
path = sys.argv[1].split("UNIX-LISTEN:")[1].split(",")[0]
s = socket.socket(socket.AF_UNIX); s.bind(path); s.listen(1)
import time; time.sleep(5)
PY
"""


def test_entrypoint_as_normal_user_just_runs_the_command(sandbox_dir):
    proc, host, _ = run_entrypoint(sandbox_dir, uid="1000", socat=None)
    assert proc.returncode == 0 and f"APP SSH={host}" in proc.stdout and "SETPRIV" not in proc.stdout


def test_entrypoint_as_root_relays_the_agent_and_drops_privileges(sandbox_dir):
    proc, host, proxy = run_entrypoint(sandbox_dir, uid="0", socat=RELAY)
    assert proc.returncode == 0, proc.stderr
    assert f"SETPRIV SSH={proxy}" in proc.stdout and f"APP SSH={proxy}" in proc.stdout


def test_entrypoint_still_starts_without_socat(sandbox_dir):
    proc, host, _ = run_entrypoint(sandbox_dir, uid="0", socat=None)
    assert proc.returncode == 0 and "SETPRIV" in proc.stdout and f"APP SSH={host}" in proc.stdout


def test_entrypoint_still_starts_if_the_relay_never_appears(sandbox_dir):
    proc, host, _ = run_entrypoint(sandbox_dir, uid="0", socat="exit 1\n")
    assert proc.returncode == 0 and f"APP SSH={host}" in proc.stdout
    assert "relay did not start" in proc.stderr


def test_entrypoint_without_a_host_socket_skips_the_relay(sandbox_dir):
    proc, host, _ = run_entrypoint(sandbox_dir, uid="0", socat=RELAY, host_socket=False)
    assert proc.returncode == 0 and "relay did not start" not in proc.stderr


def test_entrypoint_uses_a_socket_the_app_user_owns_directly(sandbox_dir):
    # Linux hosts: the mounted socket belongs to the host user, who is the app user. No relay (root could not open it).
    proc, host, proxy = run_entrypoint(sandbox_dir, uid="0", socat=RELAY, app_uid=str(os.getuid()))
    assert proc.returncode == 0, proc.stderr
    assert f"APP SSH={host}" in proc.stdout and not proxy.exists()
