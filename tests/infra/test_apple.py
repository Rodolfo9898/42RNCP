"""The Apple route on a Mac: the Makefile switch, the overlay, and scripts/apple (run with a stub `claude` and a stub `curl`, so nothing real is called)."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from tests.paths import DOCKER, ROOT, SCRIPTS

SETUP, STOP = SCRIPTS / "apple" / "apple-setup.sh", SCRIPTS / "apple" / "apple-stop.sh"
OVERLAY = DOCKER / "terminal" / "compose.apple.yml"
make_needed = pytest.mark.skipif(shutil.which("make") is None, reason="needs make")

# ------------------------------------------------------------------------------------------------------------ the Makefile

def plan(tmp_path, target, host_os, env_text=None, *args):
    """What `make -n <target>` would run on `host_os`, in a scratch folder that holds only the Makefile."""
    shutil.copy(ROOT / "Makefile", tmp_path / "Makefile")
    if env_text is not None:
        (tmp_path / ".env").write_bytes(env_text.encode())
    env = {k: v for k, v in os.environ.items() if k not in ("TERMINAL_SSH", "SANDBOX_GITHUB", "APPLE_PROXY_PORT")}
    done = subprocess.run(["make", "-n", target, f"HOST_OS={host_os}", *args], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return done.stdout


@make_needed
def test_on_a_mac_run_asks_for_the_sign_in_first_and_adds_the_apple_file(tmp_path):
    out = plan(tmp_path, "run", "Darwin")
    assert "sh scripts/apple/apple-setup.sh" in out
    assert out.index("apple-setup.sh") < out.index("docker compose"), "the sign-in comes before anything is built or started"
    up = next(line for line in out.splitlines() if line.rstrip().endswith(" up"))
    assert "-f docker-compose.yml -f docker/terminal/compose.apple.yml" in up


@make_needed
def test_on_linux_nothing_of_it_is_there(tmp_path):
    for target in ("run", "clean", "fclean"):
        out = plan(tmp_path, target, "Linux")
        assert "scripts/apple" not in out and "compose.apple.yml" not in out, target
    assert plan(tmp_path, "run", "Linux", "TERMINAL_TOKEN=x\n").count("compose.apple.yml") == 0
    assert "docker compose up" in plan(tmp_path, "run", "Linux")                        # the plain command, as before


@make_needed
def test_clean_stops_the_proxy_on_a_mac_only(tmp_path):
    assert "sh scripts/apple/apple-stop.sh" in plan(tmp_path, "clean", "Darwin")
    assert "sh scripts/apple/apple-stop.sh" in plan(tmp_path, "fclean", "Darwin")


@make_needed
def test_the_apple_file_comes_after_the_other_switches(tmp_path):
    up = next(line for line in plan(tmp_path, "run", "Darwin", "TERMINAL_SSH=1\nSANDBOX_GITHUB=1\n").splitlines() if line.rstrip().endswith(" up"))
    assert "-f docker/terminal/compose.ssh.yml -f docker/sandbox/compose.github.yml -f docker/terminal/compose.apple.yml up" in up


@make_needed
@pytest.mark.parametrize("line, expected", [("APPLE_PROXY_PORT=3600", "3600"), ("APPLE_PROXY_PORT=3600 ", "3600"), ('APPLE_PROXY_PORT="3600"', "3600"),
                                            ("# APPLE_PROXY_PORT=3600", ""), ("SOME_APPLE_PROXY_PORT=3600", "")])
def test_the_proxy_port_is_read_from_env_and_reaches_the_script(tmp_path, line, expected):
    shutil.copy(ROOT / "Makefile", tmp_path / "Makefile")
    (tmp_path / ".env").write_text(f"{line}\n")
    fake = tmp_path / "scripts" / "apple"
    fake.mkdir(parents=True)
    (fake / "apple-setup.sh").write_text('echo "port=[$APPLE_PROXY_PORT]"\n')
    env = {k: v for k, v in os.environ.items() if k != "APPLE_PROXY_PORT"}
    done = subprocess.run(["make", "apple", "HOST_OS=Darwin"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert f"port=[{expected}]" in done.stdout


# ------------------------------------------------------------------------------------------------------------ the overlay

def test_the_overlay_gives_the_terminal_a_gateway_and_nothing_else():
    text = OVERLAY.read_text()
    live = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    assert live == ["services:", "terminal:", "environment:",
                    "CLAUDE_GATEWAY_URL: http://host.docker.internal:${APPLE_PROXY_PORT:-18281}",
                    "CLAUDE_GATEWAY_TOKEN: floodgate        # a placeholder, not a secret: the proxy adds the real sign-in"]
    assert all(word not in text.split("services:")[1] for word in ("volumes", "privileged", "cap_add", "network_mode", "user:"))


def test_the_main_compose_file_has_no_gateway_so_linux_keeps_its_own_login():
    assert "CLAUDE_GATEWAY" not in (ROOT / "docker-compose.yml").read_text()
    assert "ANTHROPIC_AUTH_TOKEN" not in (ROOT / "docker-compose.yml").read_text()

# ------------------------------------------------------------------------------------------------------------ the script

def script(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class Mac:
    """A pretend Mac in a scratch folder: a stub `claude` (version, helper, diagnose, proxy start/kill) and a stub `curl`, driven by files in `state/`."""

    def __init__(self, root: Path, *, version="2.1.322 - @anthropic-ai/claude-code\n1.16.0 (@latest) - @apple/claude-code", helper=True, helper_ok=True,
                 diagnose_ok=True, answering=True, probe="200"):
        self.root, self.state, self.bin, self.home = root, root / "state", root / "bin", root / "home"
        for folder in (self.state, self.bin, self.home / ".claude"):
            folder.mkdir(parents=True)
        (self.state / "log").write_text("")
        if answering:
            (self.state / "answering").write_text("")
        (self.state / "probe").write_text(probe)
        helper_path = script(root / "helper.sh", ("echo SECRET-APPLE-TOKEN\nexit 0\n" if helper_ok else 'echo "no network" >&2\nexit 1\n'))
        settings = f'{{"apiKeyHelper": "{helper_path}", "theme": "dark"}}' if helper else '{"theme": "dark"}'
        (self.home / ".claude" / "settings.json").write_text(settings)
        script(self.bin / "claude", f'''
state="{self.state}"
echo "claude $*" >> "$state/log"
case "$1" in
  --version) printf '%s\\n' "{version}" ;;
  diagnose) {'printf "\\033[92mAll checks passed.\\033[0m\\n"' if diagnose_ok else 'echo "Checking Floodgate connectivity... failed"; exit 1'} ;;
  --start-standalone-proxy) : > "$state/answering" ;;
  --kill-standalone-proxy) rm -f "$state/answering" ;;
esac
''')
        script(self.bin / "curl", f'''
state="{self.state}"
for a in "$@"; do [ "$a" = "-w" ] && {{ echo "curl probe $*" >> "$state/log"; cat "$state/probe"; exit 0; }}; done
[ -e "$state/answering" ]
''')

    def run(self, script_path: Path, **env) -> subprocess.CompletedProcess:
        full = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.home), **env}
        return subprocess.run(["sh", str(script_path)], cwd=self.root, env=full, capture_output=True, text=True, timeout=60)

    @property
    def log(self) -> str:
        return (self.state / "log").read_text()

    @property
    def marker(self) -> Path:
        return self.root / ".apple-proxy-started"


def test_signed_in_and_the_proxy_up_is_ready_and_starts_nothing(tmp_path):
    mac = Mac(tmp_path)
    done = mac.run(SETUP)
    assert done.returncode == 0, done.stderr
    assert "apple: ready" in done.stdout and "http://127.0.0.1:18281" in done.stdout
    assert "--start-standalone-proxy" not in mac.log and not mac.marker.exists()
    assert "curl probe" in mac.log


def test_the_sign_in_token_is_never_shown(tmp_path):
    done = Mac(tmp_path).run(SETUP)
    assert "SECRET-APPLE-TOKEN" not in done.stdout + done.stderr


def test_a_proxy_that_is_down_is_started_and_remembered_so_that_clean_can_stop_it(tmp_path):
    mac = Mac(tmp_path, answering=False)
    done = mac.run(SETUP)
    assert done.returncode == 0, done.stderr
    assert "--start-standalone-proxy" in mac.log and mac.marker.exists()
    stopped = mac.run(STOP)
    assert stopped.returncode == 0 and "--kill-standalone-proxy" in mac.log and not mac.marker.exists()
    assert "stopped" in stopped.stdout


def test_a_proxy_you_started_yourself_is_not_stopped(tmp_path):
    mac = Mac(tmp_path)
    assert mac.run(SETUP).returncode == 0
    assert mac.run(STOP).returncode == 0 and "--kill-standalone-proxy" not in mac.log


def test_the_plain_claude_is_refused(tmp_path):
    mac = Mac(tmp_path, version="2.1.322 (Claude Code)")
    done = mac.run(SETUP)
    assert done.returncode == 1 and "not Apple Claude Code" in done.stderr and "nothing was started" in done.stderr
    assert "diagnose" not in mac.log


def test_without_the_sign_in_helper_it_stops(tmp_path):
    done = Mac(tmp_path, helper=False).run(SETUP)
    assert done.returncode == 1 and "apiKeyHelper" in done.stderr and "claude setup" in done.stderr


def test_a_failed_sign_in_stops_before_anything_else(tmp_path):
    mac = Mac(tmp_path, helper_ok=False, answering=False)
    done = mac.run(SETUP)
    assert done.returncode == 1 and "AppleConnect sign-in failed" in done.stderr and "no network" in done.stderr
    assert "diagnose" not in mac.log and "--start-standalone-proxy" not in mac.log and not mac.marker.exists()


def test_a_failed_health_check_stops_and_shows_why(tmp_path):
    mac = Mac(tmp_path, diagnose_ok=False, answering=False)
    done = mac.run(SETUP)
    assert done.returncode == 1 and "Floodgate connectivity... failed" in done.stderr and "did not pass" in done.stderr
    assert "--start-standalone-proxy" not in mac.log


@pytest.mark.parametrize("code", ["401", "403", "502", "000", ""])
def test_a_proxy_that_does_not_answer_the_test_request_with_200_stops_it(tmp_path, code):
    done = Mac(tmp_path, probe=code).run(SETUP)
    assert done.returncode == 1 and "200 expected" in done.stderr and "apple: ready" not in done.stdout


def test_another_port_is_never_started_for_you(tmp_path):
    mac = Mac(tmp_path, answering=False)
    done = mac.run(SETUP, APPLE_PROXY_PORT="3600")
    assert done.returncode == 1 and "port 3600" in done.stderr and "--start-standalone-proxy" not in mac.log


def test_another_port_that_answers_is_used(tmp_path):
    done = Mac(tmp_path).run(SETUP, APPLE_PROXY_PORT="3600")
    assert done.returncode == 0 and "http://127.0.0.1:3600" in done.stdout


def test_the_test_request_carries_only_a_placeholder_key_and_the_cheapest_limits():
    text = SETUP.read_text()
    assert "x-api-key: floodgate" in text and '"max_tokens":1' in text and "claude-haiku-5-5" in text
