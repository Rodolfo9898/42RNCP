"""claude, started by the Verdict extension in a VS Code terminal."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from terminal.claude.command import ClaudeCommand
from terminal.environment.child import ChildEnvironment
from terminal.projects.folders import ProjectFolders
from terminal.report.files import ReportFiles
from terminal.settings.folders import SessionFolders


class ClaudeLauncher:
    """Replaces this process by claude (`execute` is os.execvpe), in the project folder, with the review prompt and the environment of a
    review: where the subject PDFs are, where its report goes (outside the project), and nothing else."""

    def __init__(self, projects: ProjectFolders, folders: SessionFolders, reports: ReportFiles, environment: ChildEnvironment,
                 command: ClaudeCommand, execute: Callable = os.execvpe) -> None:
        self.projects, self.folders, self.reports = projects, folders, reports
        self.environment, self.command, self.execute = environment, command, execute

    def start(self, session: str, project: str, prompt_file: str) -> None:
        folder = Path(project).resolve()
        if not self.folders.is_valid(session) or not self.projects.holds(folder):
            sys.exit(f"verdict: not a review of a project in {self.projects.root}: {session!r} {project!r}")
        prompt = self._take_prompt(prompt_file)
        env = self.environment.build(session, folder)
        self.reports.prepare(session)                  # where claude's report goes
        self.reports.discard(session)                  # a new pass starts without the last one's: the extension merges what claude saves from now on
        os.chdir(folder)
        argv = self.command.interactive(prompt)
        self.execute(argv[0], argv, env)

    @staticmethod
    def _take_prompt(prompt_file: str) -> str | None:
        """The review prompt, from a file that is used once."""
        if not prompt_file:
            return None
        path = Path(prompt_file)
        try:
            return path.read_text(encoding="utf-8")
        finally:
            path.unlink(missing_ok=True)
