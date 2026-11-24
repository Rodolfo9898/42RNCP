"""src/terminal/environment/selftest.py: the environment claude works in is tested for real."""

import asyncio
import shutil

import pytest

from terminal.environment.child import ChildEnvironment
from terminal.environment.selftest import EnvironmentSelfTest

needs_toolchain = pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc") and shutil.which("c++")), reason="needs make, cc and c++")


def selftest_for(world, display, extra=None):
    extra = [("gdb", ["gdb", "--version"], False), ("claude", [str(world.stub), "--version"], True)] if extra is None else extra
    return EnvironmentSelfTest(ChildEnvironment(world.settings, display), world.scratch, extra)


@needs_toolchain
def test_selftest_really_builds_and_runs_inside_the_terminals_environment(world, display):
    got = asyncio.run(selftest_for(world, display).run())
    named = {t["name"]: t for t in got}
    assert named["claude"]["ok"] and named["claude"]["required"]            # the stub claude answers --version
    assert named["gdb"]["required"] is False                                # an extra, only in this container
    for step in ("C compiler (cc)", "C++ compiler (c++)", "make", "build C and C++ with make", "run the C program", "run the C++ program"):
        assert named[step]["ok"], named[step]
    assert list(world.scratch.iterdir()) == []                               # the scratch build is cleaned up


def test_a_probe_that_cannot_start_is_reported_not_raised(world, display):
    got = asyncio.run(selftest_for(world, display, [("nothing", ["definitely-not-a-command"], True)]).run())
    assert {t["name"]: t for t in got}["nothing"]["ok"] is False


def test_the_selftest_runs_in_claudes_environment_without_secrets(world, display, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-not-leak")
    outcome = selftest_for(world, display)._execute(["sh", "-c", "echo $ANTHROPIC_API_KEY$TERMINAL_TOKEN; echo $HOME"], world.scratch, 10)
    assert outcome.rc == 0 and outcome.stdout.split() == [str(world.tmp / "home")]
