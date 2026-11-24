"""The folder of projects (shared with the terminal container) and which project a session is about."""

from __future__ import annotations

from pathlib import Path

from verdict.repository import repo as repo_mod
from verdict.sessions.store import Session


class ProjectFolders:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def of(self, session: Session) -> Path | None:
        """Where this session's clone lives (always inside the projects folder)."""
        if not session.repo or not session.repo.path:
            return None
        try:
            return repo_mod.safe_path(self.root, session.repo.path)
        except repo_mod.RepoError:
            return None

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root.resolve()).as_posix()

    def listing(self) -> dict:
        """The sub-folders a clone can be placed in, and the folders that can be reviewed where they are."""
        return {"root": self.root.name, "folders": repo_mod.list_folders(self.root), "existing": repo_mod.list_existing(self.root)}
