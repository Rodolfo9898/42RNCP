"""Walking the projects folder to suggest destinations and to find what can be reviewed in place."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class FolderWalker(ABC):
    """Template Method: walks the folders under a root down to a depth; the subclasses decide which folders count, what is
    reported for each and whether to look inside it."""

    depth = 2

    def __init__(self, depth: int | None = None) -> None:
        self.depth = self.depth if depth is None else depth

    @abstractmethod
    def accepts(self, child: Path) -> bool: ...

    @abstractmethod
    def entry(self, rel: str, child: Path): ...

    def descends(self, child: Path) -> bool:
        return True

    def walk(self, root: Path) -> list:
        out: list = []
        self._walk(root, "", 1, out)
        return out

    def _walk(self, base: Path, prefix: str, level: int, out: list) -> None:
        if level > self.depth or not base.is_dir():
            return
        for child in sorted(base.iterdir()):
            if not self.accepts(child):
                continue
            rel = f"{prefix}{child.name}"
            out.append(self.entry(rel, child))
            if self.descends(child):
                self._walk(child, rel + "/", level + 1, out)
