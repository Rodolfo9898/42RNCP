"""The two listings of the projects folder: where a clone may go, and what can be reviewed where it is."""

from __future__ import annotations

from pathlib import Path

from verdict.repository.repo.address.names import NAME_RE
from verdict.repository.repo.address.paths import ProjectsFolder
from verdict.repository.repo.folders.walker import FolderWalker
from verdict.repository.repo.git.client import GitClient
from verdict.repository.repo.git.inspector import FolderInspector
from verdict.repository.repo.model.records import RepoInfo


class DestinationFolders(FolderWalker):
    """Existing non-repository folders, as destination suggestions."""

    depth = 2

    def accepts(self, child: Path) -> bool:
        return child.is_dir() and not child.is_symlink() and not (child / ".git").exists() and not child.name.startswith(".")

    def entry(self, rel: str, child: Path) -> str:
        return rel


class ReviewableFolders(FolderWalker):
    """Folders that can be reviewed in place: {"path", "git"}. A git repository is not searched inside."""

    depth = 3

    def accepts(self, child: Path) -> bool:
        return not child.is_symlink() and child.is_dir() and not child.name.startswith(".") and bool(NAME_RE.match(child.name))

    def entry(self, rel: str, child: Path) -> dict:
        return {"path": rel, "git": (child / ".git").exists()}

    def descends(self, child: Path) -> bool:
        return not (child / ".git").exists()


def list_folders(root: Path, depth: int = 2) -> list[str]:
    """Existing non-repository folders under `root`, as destination suggestions."""
    return DestinationFolders(depth).walk(root)


def list_existing(root: Path, depth: int = 3) -> list[dict]:
    """Folders under `root` that can be reviewed in place: {"path", "git"}. A git repository is not searched inside."""
    return ReviewableFolders(depth).walk(root)


def use_existing(root: Path, rel: str, inspector: FolderInspector | None = None) -> tuple[Path, RepoInfo]:
    """An existing folder inside the projects folder, reviewed where it is (no clone, nothing copied or deleted)."""
    path = ProjectsFolder(root).existing(rel)
    return path, (inspector or FolderInspector(GitClient.offline())).info(path)
