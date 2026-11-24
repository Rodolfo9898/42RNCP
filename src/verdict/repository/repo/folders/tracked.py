"""Which files a repository has."""

from __future__ import annotations

import os
from pathlib import Path


def tracked_files(root: Path) -> list[Path]:
    """Every regular file in the repo (relative paths), ignoring .git and symlinks."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if not path.is_symlink():
                out.append(path.relative_to(root))
    return out
