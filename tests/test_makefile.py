"""The Makefile's switches, read with `make -n` (prints what it would run, runs nothing) in a scratch folder with its own .env."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="needs make")


def uses_the_ssh_file(tmp_path, env_text=None, *args):
    """Would `make run` start the containers with docker-compose.ssh.yml (the terminal gets your ssh-agent)?"""
    shutil.copy(ROOT / "Makefile", tmp_path / "Makefile")
    if env_text is not None:
        (tmp_path / ".env").write_bytes(env_text.encode())
    env = {k: v for k, v in os.environ.items() if k != "TERMINAL_SSH"}          # (a TERMINAL_SSH exported in your shell would win)
    done = subprocess.run(["make", "-n", "run", *args], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    up = [line for line in done.stdout.splitlines() if line.rstrip().endswith(" up")]
    assert len(up) == 1, done.stdout
    return "docker-compose.ssh.yml" in up[0]


@pytest.mark.parametrize("line", ["TERMINAL_SSH=1", "TERMINAL_SSH=1 ", "TERMINAL_SSH=1\t", "TERMINAL_SSH=1\r", 'TERMINAL_SSH="1"', "TERMINAL_SSH= 1"])
def test_the_ssh_switch_in_env_works_whatever_whitespace_or_quotes_surround_the_1(tmp_path, line):
    assert uses_the_ssh_file(tmp_path, f"TERMINAL_TOKEN=x\n{line}\n"), repr(line)


@pytest.mark.parametrize("line", ["TERMINAL_SSH=0", "TERMINAL_SSH=", "TERMINAL_SSH=yes", "TERMINAL_SSH=11", "# TERMINAL_SSH=1", "SOME_TERMINAL_SSH=1"])
def test_anything_but_a_one_leaves_the_agent_away_from_the_terminal(tmp_path, line):
    assert not uses_the_ssh_file(tmp_path, f"TERMINAL_TOKEN=x\n{line}\n"), repr(line)


def test_off_by_default_and_on_from_the_command_line(tmp_path):
    assert not uses_the_ssh_file(tmp_path)                                         # no .env at all
    assert uses_the_ssh_file(tmp_path, "TERMINAL_TOKEN=x\n", "TERMINAL_SSH=1")
    assert uses_the_ssh_file(tmp_path, "TERMINAL_SSH=0\n", "TERMINAL_SSH=1")        # the command line wins over .env
    assert uses_the_ssh_file(tmp_path, "TERMINAL_TOKEN=x\n", "TERMINAL_SSH=1 ")       # a space typed after the 1 on the command line
