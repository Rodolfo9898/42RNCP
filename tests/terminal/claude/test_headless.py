"""src/terminal/claude/headless.py: the one-click review, a headless claude on a sanitized copy."""

import asyncio
import stat
import time
from dataclasses import replace

import pytest

from terminal.claude.command import ClaudeCommand
from terminal.claude.headless import HeadlessReview, ReviewFailed
from terminal.environment.child import ChildEnvironment
from terminal.projects.folders import ProjectFolders
from terminal.projects.sanitizer import SanitizedCopy
from terminal.settings.limits import Limits


def review_for(world, display, **changes):
    settings = replace(world.settings, **changes)
    environment = ChildEnvironment(settings, display)
    return HeadlessReview(ClaudeCommand(settings.claude), environment, ProjectFolders(settings.projects), SanitizedCopy(settings, environment),
                          settings.limits.review_timeout)


async def connected():
    return False


def run(review, body, disconnected=connected):
    return asyncio.run(review.run(body, disconnected))


def body(**changes):
    return {"repo": "42/ps", "prompt": "Look at the code.", "schema": {"type": "object"}, **changes}


def test_review_runs_headless_claude_on_a_copy_and_cleans_up(world, display):
    data = run(review_for(world, display), body())
    assert data["returncode"] == 0 and '"result": "reviewed"' in data["stdout"]
    assert "--tools Read,Grep,Glob" in data["stdout"] and "--permission-mode dontAsk" in data["stdout"]
    assert list(world.scratch.iterdir()) == []


@pytest.mark.parametrize("bad", [body(repo="../outside"), body(repo="missing"), {"repo": "42/ps"}, {"repo": "42/ps", "prompt": "x"},
                                 {"repo": "42/ps", "prompt": "x", "schema": 5}, body(timeout="soon"), ["not", "an", "object"]])
def test_review_needs_a_valid_repository_and_a_complete_request(world, display, bad):
    with pytest.raises(ReviewFailed) as refused:
        run(review_for(world, display), bad)
    assert refused.value.status == 400 and list(world.scratch.iterdir()) == []


def test_a_repository_too_large_to_copy_is_refused(world, display):
    with pytest.raises(ReviewFailed) as refused:
        run(review_for(world, display, limits=Limits(max_copy_files=1)), body())
    assert refused.value.status == 400 and "too large" in refused.value.detail and list(world.scratch.iterdir()) == []


def slow_claude(world):
    world.stub.write_text("#!/bin/sh\nsleep 30\n")
    world.stub.chmod(world.stub.stat().st_mode | stat.S_IEXEC)


def test_review_times_out(world, display):
    slow_claude(world)
    start = time.monotonic()
    with pytest.raises(ReviewFailed) as slow:
        run(review_for(world, display), body(timeout=1))
    assert slow.value.status == 504 and time.monotonic() - start < 10
    assert list(world.scratch.iterdir()) == []


def test_claude_is_stopped_when_the_app_gives_up(world, display):
    slow_claude(world)

    async def gone():
        return True

    start = time.monotonic()
    with pytest.raises(ReviewFailed) as stopped:
        run(review_for(world, display), body(), disconnected=gone)
    assert stopped.value.status == 499 and time.monotonic() - start < 10
    assert list(world.scratch.iterdir()) == []


def test_the_default_timeout_comes_from_the_limits(world, display):
    slow_claude(world)
    start = time.monotonic()
    with pytest.raises(ReviewFailed) as slow:
        run(review_for(world, display, limits=Limits(review_timeout=1)), body())
    assert slow.value.status == 504 and time.monotonic() - start < 10


def test_the_headless_claude_gets_no_secret_of_the_service(world, display, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-not-leak")                      # (in this process's own environment too)
    monkeypatch.setenv("TERMINAL_TOKEN", "t0ken-for-tests")
    world.stub.write_text('#!/bin/sh\necho "{\\"env\\": \\"$(env | grep -E \'TOKEN|API_KEY|SECRET\' | tr \'\\n\' \' \')\\"}"\n')
    world.stub.chmod(world.stub.stat().st_mode | stat.S_IEXEC)
    data = run(review_for(world, display), body())
    assert data["returncode"] == 0 and "sk-must-not-leak" not in data["stdout"] and "t0ken-for-tests" not in data["stdout"]
    assert '"env": ""' in data["stdout"]
