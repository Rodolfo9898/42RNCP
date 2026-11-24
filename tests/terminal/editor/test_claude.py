"""src/terminal/editor/claude.py: claude, started by the Verdict extension in a VS Code terminal (`python -m editor_launcher claude ...`)."""

import stat
import subprocess
import sys
from pathlib import Path

import pytest

from terminal.claude.command import ClaudeCommand
from terminal.claude.prompts import APPEND_PROMPT_LIVE
from terminal.editor.claude import ClaudeLauncher
from terminal.environment.child import ChildEnvironment
from terminal.projects.folders import ProjectFolders
from terminal.report.files import ReportFiles
from tests.paths import SRC
from tests.terminal.fakes import environment_of


def launcher_for(world, display, started):
    settings = world.settings
    return ClaudeLauncher(ProjectFolders(settings.projects), settings.folders, ReportFiles(settings.folders), ChildEnvironment(settings, display),
                          ClaudeCommand("claude"), execute=lambda exe, argv, env: started.update(exe=exe, argv=argv, env=env, cwd=Path.cwd()))


@pytest.fixture
def project(world):
    folder = world.projects / "cub3d"
    folder.mkdir()
    return folder


def test_claude_is_only_started_in_a_project_and_for_a_real_review(world, display, project, monkeypatch):
    monkeypatch.chdir(world.tmp)
    started = {}
    launcher = launcher_for(world, display, started)
    for session, folder in (("abcdef123", "/etc"), ("../../x", str(project)), ("abcdef123", str(world.tmp)), ("abcdef123", str(project / "missing")),
                            ("abcdef123", str(project / "x.c")), ("", str(project)), ("short", str(project))):
        with pytest.raises(SystemExit):
            launcher.start(session, folder, "")
    assert started == {}, "nothing was started"
    link = world.projects / "escape"
    link.symlink_to("/etc")
    with pytest.raises(SystemExit):
        launcher.start("abcdef123", str(link), "")                                # a link out of the projects is not in them


def test_claude_starts_in_the_project_with_the_prompt_and_its_report_outside(world, display, project, monkeypatch):
    prompt = world.tmp / "prompt.txt"
    prompt.write_text("review this")
    monkeypatch.chdir(world.tmp)
    started = {}
    launcher_for(world, display, started).start("abcdef123", str(project), str(prompt))
    assert started["argv"][-1] == "review this" and started["cwd"] == project.resolve() and started["exe"] == "claude"
    assert started["argv"][1:3] == ["--allowedTools", "Bash(readpdf:*)"] and APPEND_PROMPT_LIVE in started["argv"]
    assert started["env"]["REPORT_DIR"] == str(world.reports / "abcdef123") and Path(started["env"]["REPORT_DIR"]).is_dir()
    assert started["env"]["SUBJECTS_DIR"] == str(world.subjects / "abcdef123")
    assert started["env"]["GIT_CONFIG_VALUE_0"] == str(project.resolve()), "git trusts this folder only"
    assert not prompt.exists(), "the prompt file is used once"
    assert not any(k in started["env"] for k in ("TERMINAL_TOKEN", "EDITOR_TOKEN", "ANTHROPIC_API_KEY"))


def test_without_a_prompt_file_claude_starts_empty_handed(world, display, project, monkeypatch):
    monkeypatch.chdir(world.tmp)
    started = {}
    launcher_for(world, display, started).start("abcdef123", str(project), "")
    assert started["argv"] == ClaudeCommand("claude").interactive()


def test_a_prompt_file_that_is_not_there_stops_the_launch(world, display, project, monkeypatch):
    monkeypatch.chdir(world.tmp)
    started = {}
    with pytest.raises(FileNotFoundError):
        launcher_for(world, display, started).start("abcdef123", str(project), str(world.tmp / "gone.txt"))
    assert started == {}


def test_a_new_pass_starts_without_the_report_of_the_last_one(world, display, project, monkeypatch):
    old = world.reports / "abcdef123" / "claude-review.md"
    old.parent.mkdir(parents=True)
    old.write_text("# the report of the last pass")
    (old.parent / "notes.txt").write_text("not a report")
    monkeypatch.chdir(world.tmp)
    launcher = launcher_for(world, display, {})
    launcher.start("abcdef123", str(project), "")
    assert not old.exists(), "or it would be merged as if claude had just written it"
    assert (old.parent / "notes.txt").exists()
    launcher.start("abcdef123", str(project), "")                                # and a folder without one is fine


def test_the_launcher_command_line_works_end_to_end_as_the_extension_runs_it(world, project, tmp_path):
    """The exact command of the Verdict extension, in a real process that really becomes claude (here a stub that shows how it was started)."""
    stub = tmp_path / "bin" / "claude"
    stub.parent.mkdir()
    stub.write_text('#!/bin/sh\necho "ARGV: $# $1 $2"\necho "LAST: $(for last; do :; done; echo "$last")"\necho "CWD: $(pwd)"\n'
                    'echo "REPORT_DIR: $REPORT_DIR"\necho "SUBJECTS_DIR: $SUBJECTS_DIR"\necho "TOKEN: [$TERMINAL_TOKEN$EDITOR_TOKEN$ANTHROPIC_API_KEY]"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("review this one")
    environ = {**environment_of(tmp_path, CLAUDE_BIN=str(stub)), "PATH": str(tmp_path / "empty"), "PYTHONPATH": str(SRC)}
    (tmp_path / "empty").mkdir()
    done = subprocess.run([sys.executable, "-m", "editor_launcher", "claude", "--session", "abcdef123", "--project", str(project),
                           "--prompt-file", str(prompt)], capture_output=True, text=True, env=environ, cwd=tmp_path, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "ARGV: " in done.stdout and "LAST: review this one" in done.stdout and f"CWD: {project.resolve()}" in done.stdout
    assert f"REPORT_DIR: {world.reports / 'abcdef123'}" in done.stdout and f"SUBJECTS_DIR: {world.subjects / 'abcdef123'}" in done.stdout
    assert "TOKEN: []" in done.stdout and not prompt.exists()
    refused = subprocess.run([sys.executable, "-m", "editor_launcher", "claude", "--session", "abcdef123", "--project", "/etc"],
                             capture_output=True, text=True, env=environ, cwd=tmp_path, timeout=60)
    assert refused.returncode != 0 and "not a review of a project" in refused.stderr
