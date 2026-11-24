"""Which files of a repository are the student's own, and how to read them."""

from __future__ import annotations

from pathlib import Path

from shared.constants import GENERATED_VERDICT_NAMES, VERDICT_MARKER
from verdict.checks import EXCLUDED_DIRS, minilibx_dirs
from verdict.repository.repo import tracked_files

MAX_FILE_BYTES = 300_000


def priority(rel: Path) -> int:
    """Lower is shown first: the README, the Makefile and the headers say the most about a project."""
    name = rel.name.lower()
    if name.startswith("readme"):
        return 0
    if name in ("makefile", "gnumakefile") or name.endswith(".mk"):
        return 1
    if rel.suffix in (".h", ".hpp"):
        return 2
    if name.startswith("main."):
        return 3
    if rel.suffix in (".c", ".cpp", ".cc", ".tpp", ".ipp", ".py", ".js", ".ts", ".go", ".rs", ".java", ".sh"):
        return 4
    return 5


def read_text(path: Path) -> str | None:
    """The text of a file, or None when it is too big, unreadable or binary."""
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


class StudentFiles:
    """The files of the repository at `root` that the review looks at (the one filter that the digest and the line index share).

    Left out: .git and MiniLibX (whatever its folder is called: it is given to the students), and the generated verdict itself."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def listing(self) -> list[Path]:
        files = tracked_files(self.root)
        mlx = tuple(d + "/" for d in minilibx_dirs(self.root, files))
        return [rel for rel in files if not self._left_out(rel, mlx)]

    def _left_out(self, rel: Path, mlx: tuple[str, ...]) -> bool:
        posix = rel.as_posix()
        return bool(EXCLUDED_DIRS.search("/" + posix)) or posix.startswith(mlx) or self._is_generated_verdict(rel)

    def _is_generated_verdict(self, rel: Path) -> bool:
        if len(rel.parts) != 1 or rel.name not in GENERATED_VERDICT_NAMES:
            return False
        try:
            return (self.root / rel).read_bytes()[:200].startswith(VERDICT_MARKER.encode())
        except OSError:
            return False
