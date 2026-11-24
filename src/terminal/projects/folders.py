"""The projects folder: where claude works, and the only place a path from outside may point into."""

from pathlib import Path


class ProjectFolders:
    """The projects folder of the user's machine (mounted into the container). A path is only accepted when it stays inside it."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def resolve(self, relative: str) -> Path:
        """A directory inside the projects folder, from a path relative to it; never a path that escapes it."""
        if not relative or relative.startswith(("/", "~")) or "\\" in relative or ".." in Path(relative).parts:
            raise ValueError("invalid repository path")
        root = self.root.resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_dir():
            raise ValueError("repository not found")
        return target

    def holds(self, folder: Path) -> bool:
        """Is `folder` (already resolved) an existing directory inside the projects folder?"""
        return folder.is_dir() and folder.is_relative_to(self.root.resolve())
