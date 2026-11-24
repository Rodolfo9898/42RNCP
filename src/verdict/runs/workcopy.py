"""The disposable copy of a project where the checks build and run things."""

from __future__ import annotations

import shutil
from pathlib import Path

from verdict.sessions.store import Session


class WorkCopy:
    """The clone itself is never built in, so it always shows exactly what was committed (no .o files or binaries left over from a
    previous run). The copy is a git repository too (its .git, without hooks), so git works in the sandbox."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def make(self, session: Session, clone: Path) -> Path:
        work = self.workspace / session.id / "work"
        shutil.rmtree(work, ignore_errors=True)
        shutil.copytree(clone, work, symlinks=True, ignore=lambda folder, names: ["hooks"] if Path(folder) == clone / ".git" else [])
        return work

    @staticmethod
    def remove(work: Path) -> None:
        shutil.rmtree(work, ignore_errors=True)
