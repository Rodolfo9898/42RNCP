"""src/terminal/claude/onboarding.py: claude's first-run wizard is skipped when it goes through a gateway, and only then."""

import json
import os
import stat
from dataclasses import replace

import pytest

from terminal.claude.onboarding import FirstRun

GATEWAY = {"claude_gateway_url": "http://host.docker.internal:18281", "claude_gateway_token": "floodgate"}


def first_run(world, **changes):
    return FirstRun(replace(world.settings, **changes))


def config(world):
    return world.tmp / "home" / ".claude" / ".claude.json"


def test_without_a_gateway_nothing_is_written_and_you_log_in_as_before(world):
    assert first_run(world).prepare() is False
    assert not config(world).exists() and not config(world).parent.exists()


def test_with_a_gateway_a_new_config_folder_gets_the_flag_that_skips_the_wizard(world):
    assert first_run(world, **GATEWAY).prepare() is True
    assert json.loads(config(world).read_text()) == {"hasCompletedOnboarding": True}
    assert stat.S_IMODE(config(world).stat().st_mode) == 0o600                  # private to its owner, like claude's own files
    assert [p.name for p in config(world).parent.iterdir()] == [".claude.json"]  # (no temporary file left behind)


def test_it_is_done_once_and_the_second_start_changes_nothing(world):
    first_run(world, **GATEWAY).prepare()
    before = config(world).stat().st_mtime_ns
    assert first_run(world, **GATEWAY).prepare() is False
    assert config(world).stat().st_mtime_ns == before


def test_what_claude_wrote_in_the_file_is_kept(world):
    config(world).parent.mkdir(parents=True)
    config(world).write_text(json.dumps({"numStartups": 7, "theme": "light", "projects": {"/projects/x": {"hasTrustDialogAccepted": True}}}))
    assert first_run(world, **GATEWAY).prepare() is True
    assert json.loads(config(world).read_text()) == {"numStartups": 7, "theme": "light", "hasCompletedOnboarding": True,
                                                     "projects": {"/projects/x": {"hasTrustDialogAccepted": True}}}


def test_a_wizard_that_is_already_done_is_not_touched(world):
    config(world).parent.mkdir(parents=True)
    text = '{"hasCompletedOnboarding":true,  "oauthAccount": {"emailAddress": "me@example.com"}}'
    config(world).write_text(text)
    assert first_run(world, **GATEWAY).prepare() is False
    assert config(world).read_text() == text                                      # byte for byte


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '"text"', ""])
def test_a_file_that_is_not_a_json_object_is_left_alone(world, content):
    config(world).parent.mkdir(parents=True)
    config(world).write_text(content)
    assert first_run(world, **GATEWAY).prepare() is False
    assert config(world).read_text() == content


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_a_folder_that_cannot_be_written_does_not_stop_the_start(world):
    config(world).parent.mkdir(parents=True)
    config(world).parent.chmod(0o500)
    try:
        assert first_run(world, **GATEWAY).prepare() is False
    finally:
        config(world).parent.chmod(0o700)
    assert not config(world).exists()
