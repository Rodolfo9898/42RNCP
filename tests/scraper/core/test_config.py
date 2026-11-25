"""src/scraper/core/config.py: the session files follow SESSION_DIR."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from scraper.core.config import ROOT, Settings


def test_by_default_the_session_is_kept_in_the_repository():
    s = Settings()
    assert s.session_dir == ROOT / ".session"
    assert (s.state_file, s.user_agent_file) == (ROOT / ".session" / "state.json", ROOT / ".session" / "user_agent.txt")


def test_the_two_session_files_derive_from_the_session_folder():
    s = Settings(session_dir=Path("/session"))
    assert (s.state_file, s.user_agent_file) == (Path("/session/state.json"), Path("/session/user_agent.txt"))


def test_a_file_given_explicitly_wins_over_the_folder():
    s = Settings(session_dir=Path("/session"), state_file=Path("/elsewhere/cookies.json"))
    assert s.state_file == Path("/elsewhere/cookies.json") and s.user_agent_file == Path("/session/user_agent.txt")


def test_a_copy_with_other_options_keeps_the_session_where_it_was():
    s = replace(Settings(session_dir=Path("/session")), with_artifacts=False, with_children=False)
    assert s.state_file == Path("/session/state.json") and s.with_artifacts is False


def test_session_dir_comes_from_the_environment_and_the_files_follow():
    s = Settings.from_env(environ={"SESSION_DIR": "/mnt/session"})
    assert s.session_dir == Path("/mnt/session") and s.state_file == Path("/mnt/session/state.json")
    assert s.user_agent_file == Path("/mnt/session/user_agent.txt")
    assert Settings.from_env(environ={}).session_dir == ROOT / ".session" and Settings.from_env(environ={"SESSION_DIR": ""}).session_dir == ROOT / ".session"


def test_the_other_variables_are_read_from_the_mapping_it_is_given():
    s = Settings.from_env(environ={"SAMPLES_DIR": "/s", "ARTIFACTS_DIR": "/a", "SUBJECT_LANG": "FR", "SCRAPE_DELAY": "0.5",
                                   "INTRA_LOGIN": "me", "INTRA_PASSWORD": "pw", "HEADLESS": "false", "BROWSER_CHANNEL": "chromium"})
    assert (s.samples_dir, s.artifacts_dir, s.lang, s.delay) == (Path("/s"), Path("/a"), "fr", 0.5)
    assert (s.login, s.password, s.headless, s.browser_channel) == ("me", "pw", False, "chromium")
    assert Settings.from_env(lang="de", delay=0, environ={"SUBJECT_LANG": "fr", "SCRAPE_DELAY": "9"}).lang == "de"
    assert Settings.from_env(lang="de", delay=0, environ={"SUBJECT_LANG": "fr", "SCRAPE_DELAY": "9"}).delay == 0
