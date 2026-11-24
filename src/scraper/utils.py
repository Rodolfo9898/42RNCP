"""Small helpers with no dependencies on the rest of the package."""
from __future__ import annotations

import os
import re
from pathlib import Path


def safe_name(name: str) -> str:
    """Make a string safe to use as a file or folder name."""
    name = re.sub(r'[\x00-\x1f/\\:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "unnamed"


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def first_line(exc: BaseException) -> str:
    return (str(exc).splitlines() or [type(exc).__name__])[0]


def prune_empty(path: Path, root: Path) -> None:
    """Remove `path` and its parents (never `root` itself) for as long as they are empty. A missing `path` is skipped."""
    while path != root and root in path.parents:
        if path.exists():
            try:
                path.rmdir()
            except OSError:      # not empty: the parents aren't either
                break
        path = path.parent


def load_env(path: Path) -> None:
    """Put the KEY=value lines of a .env file into the environment (what is already set wins). No quoting rules beyond
    stripping one pair of matching quotes: enough for INTRA_LOGIN and INTRA_PASSWORD."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        key = key.strip().removeprefix("export ").strip()
        if key:
            os.environ.setdefault(key, value)
