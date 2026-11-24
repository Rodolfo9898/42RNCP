"""What a folder says about itself: where it came from and its last commit."""

from __future__ import annotations

import subprocess
from pathlib import Path

from verdict.repository.repo.git.client import GitClient
from verdict.repository.repo.model.records import RepoInfo

LOG_FORMAT = "--format=%h%n%s%n%an"


class FolderInspector:
    """Reads the git state of a folder (nothing is run from it, nothing is changed)."""

    def __init__(self, client: GitClient) -> None:
        self.client = client

    def _git(self, folder: Path, *args: str) -> str:
        try:
            return self.client.run(*args, folder=folder).stdout
        except (subprocess.TimeoutExpired, OSError):
            return ""

    def last_commit(self, folder: Path, url: str = "") -> RepoInfo:
        """`url` with the abbreviated hash, subject and author of the last commit (empty fields when there is none)."""
        log = self._git(folder, "log", "-1", LOG_FORMAT).splitlines() + ["", "", ""]
        return RepoInfo(url=url, commit=log[0], subject=log[1], author=log[2])

    def info(self, folder: Path) -> RepoInfo:
        """Remote and last commit of a folder; empty fields when it is not a git repository."""
        if not (folder / ".git").exists():
            return RepoInfo(url="", commit="", subject="", author="")
        return self.last_commit(folder, self._git(folder, "config", "--get", "remote.origin.url").strip())
