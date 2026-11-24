"""Code the students were given (MiniLibX): it is found by what a folder holds, not by what the folder is called."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

EXCLUDED_DIRS = re.compile(r"(^|/)(mlx|minilibx[\w.-]*|mlx_linux|mlx42|libmlx[\w.-]*|\.git)/", re.I)
# The 42 header the Norm asks for: code that has it was written by a student, not vendored.
HEADER_42 = re.compile(rb"By: \S+.*<.*>.*\n.*\n?.*Created: ", re.I)


def minilibx_dirs(root: Path, files: Iterable[Path]) -> list[str]:
    """The folders (relative to `root`) that hold a copy of MiniLibX, whatever they are called: a folder with mlx.h next to other
    mlx_* files (the classic MiniLibX), or the root of MLX42 (include/MLX42/MLX42.h). MiniLibX is given to the students, so it is
    not their code: the Norm and the code checks leave it out. The project's own root is never one of them."""
    by_dir: dict[Path, set[str]] = {}
    found: set[str] = set()
    for rel in files:
        by_dir.setdefault(rel.parent, set()).add(rel.name)
        if rel.name == "MLX42.h" and rel.parent.name == "MLX42" and rel.parent.parent.name == "include":
            found.add(rel.parent.parent.parent.as_posix())
    for folder, names in by_dir.items():
        if "mlx.h" in names and any(n != "mlx.h" and n.startswith("mlx_") for n in names):
            found.add(folder.as_posix())
    return sorted(f for f in found if f not in ("", "."))
