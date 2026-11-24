"""Where things live inside the projects folder. Every path that comes from outside is checked to stay inside it."""

from __future__ import annotations

from pathlib import Path

from verdict.repository.repo.address.names import NAME_RE
from verdict.repository.repo.model.errors import RepoError


class ProjectsFolder:
    """The folder that holds the projects: turns what the user typed into a path that cannot leave it (Guard)."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def destination(self, destination: str, name: str) -> Path:
        """Where a clone will live: <root>/<destination>/<name>. Never outside the root, never an existing path."""
        if not NAME_RE.match(name):
            raise RepoError("The project name may only contain letters, digits, '.', '_' and '-' (max 100 characters).")
        destination = destination.strip()
        if destination.startswith(("/", "~")) or "\\" in destination:
            raise RepoError("The destination is a folder inside the projects folder, e.g. 42/common-core (not an absolute path).")
        parts = [p for p in destination.split("/") if p]
        for part in parts:
            if not NAME_RE.match(part):
                raise RepoError(f"Invalid folder name in the destination: {part!r}.")
        target = self.root.joinpath(*parts, name)
        if not target.parent.resolve().is_relative_to(self.root):  # a symlinked folder pointing outside
            raise RepoError("The destination leaves the projects folder.")
        if target.exists() or target.is_symlink():
            raise RepoError(f"{target.relative_to(self.root).as_posix()} already exists. Choose another name or destination.")
        return target

    def existing(self, rel: str) -> Path:
        """An existing folder of the projects folder, to be reviewed where it is (no clone, nothing copied or deleted)."""
        rel = rel.strip().strip("/")
        parts = [p for p in rel.split("/") if p]
        if not parts or rel.startswith("~") or "\\" in rel or not all(NAME_RE.match(p) for p in parts):
            raise RepoError("Choose a folder inside the projects folder, e.g. 42/common-core/push_swap.")
        path = self.root.joinpath(*parts)
        if any(self.root.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1)):
            raise RepoError("That folder is a symbolic link; choose the real folder.")
        if not path.is_dir() or not path.resolve().is_relative_to(self.root):
            raise RepoError(f"{rel} is not a folder inside the projects folder.")
        return path

    def inside(self, rel: str) -> Path:
        """Resolve `rel` inside the root; refuse traversal and symlinks that leave it."""
        target = (self.root / rel).resolve()
        if target != self.root and not target.is_relative_to(self.root):
            raise RepoError("path escapes the repository")
        return target


def resolve_destination(root: Path, destination: str, name: str) -> Path:
    """Where a clone will live: <root>/<destination>/<name>. Never outside `root`, never an existing path."""
    return ProjectsFolder(root).destination(destination, name)


def safe_path(root: Path, rel: str) -> Path:
    """Resolve `rel` inside `root`; refuse traversal and symlinks that leave the repo."""
    return ProjectsFolder(root).inside(rel)
