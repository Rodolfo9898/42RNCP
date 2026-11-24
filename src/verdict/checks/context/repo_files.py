"""The repository as the checks see it."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from shared.constants import GENERATED_VERDICT_NAMES, VERDICT_MARKER
from verdict.checks.context.memo import memo
from verdict.checks.context.vendored import EXCLUDED_DIRS, HEADER_42, minilibx_dirs
from verdict.repository.repo import submodule_paths, tracked_files

SOURCE_EXTS = frozenset({".c", ".h", ".cpp", ".hpp", ".tpp", ".ipp", ".cc"})


class RepoFiles:
    """A read-only view of the files of one repository (Facade over the tree): which ones are the project's own, which are code
    it was given (MiniLibX) or lives in a submodule, and how to read them. Computed once, in the review's `cache`."""

    def __init__(self, repo: Path, cache: dict[str, Any]) -> None:
        self.repo, self.cache = repo, cache

    def submodule_paths(self) -> list[str]:
        return memo(self.cache, "submodule_paths", lambda: submodule_paths(self.repo))

    def minilibx_dirs(self) -> list[str]:
        return memo(self.cache, "minilibx_dirs", lambda: minilibx_dirs(self.repo, tracked_files(self.repo)))

    def is_vendored(self, rel: Path | str) -> bool:
        """Code given to the students (MiniLibX, under any folder name) rather than written by them."""
        posix = rel.as_posix() if isinstance(rel, Path) else str(rel)
        return bool(EXCLUDED_DIRS.search("/" + posix)) or any(posix.startswith(d + "/") for d in self.minilibx_dirs())

    def student_submodule_files(self) -> list[Path]:
        """Files of the submodules the student wrote (their libft, ft_printf...): a submodule is a way to copy their own code into the
        project, so the Norm applies to it. A submodule counts as theirs when one of its C files has the 42 header; MiniLibX never does."""
        return memo(self.cache, "student_submodule_files", self._student_submodule_files)

    def _student_submodule_files(self) -> list[Path]:
        out: list[Path] = []
        for module in self.submodule_paths():
            base = self.repo / module
            if not base.is_dir():
                continue
            files = [Path(module) / p for p in tracked_files(base)]
            sources = [p for p in files if p.suffix.lower() in (".c", ".h") and not self.is_vendored(p)]
            if any(HEADER_42.search((self.repo / p).read_bytes()[:2000]) for p in sources[:200] if (self.repo / p).is_file()):
                out += sources
        return out

    def files(self) -> list[Path]:
        """The project's own files: not the generated verdict, and not what lives in its submodules (those are other repositories)."""
        return memo(self.cache, "files", self._own_files)

    def _own_files(self) -> list[Path]:
        modules = tuple(m.rstrip("/") + "/" for m in self.submodule_paths())
        return [p for p in tracked_files(self.repo) if not self._is_generated_verdict(p) and not p.as_posix().startswith(modules)]

    def _is_generated_verdict(self, rel: Path) -> bool:
        if len(rel.parts) != 1 or rel.name not in GENERATED_VERDICT_NAMES:
            return False
        try:
            return (self.repo / rel).open("rb").read(200).startswith(VERDICT_MARKER.encode())
        except OSError:
            return False

    def walk(self, base: Path) -> list[Path]:
        """Fresh listing of `base` (the cached `files()` goes stale once the repo is built)."""
        return tracked_files(base)

    def source_files(self, unit: str = ".", *, exclude_vendored: bool = True) -> list[Path]:
        """Source files (relative to the repo root) under `unit`."""
        prefix = "" if unit in (".", "") else unit.rstrip("/") + "/"
        out = []
        for p in self.files():
            s = p.as_posix()
            if p.suffix.lower() in SOURCE_EXTS and s.startswith(prefix):
                if exclude_vendored and self.is_vendored(s):
                    continue
                out.append(p)
        return out

    def read(self, rel: Path) -> str:
        try:
            return (self.repo / rel).read_bytes()[:1_000_000].decode("utf-8", errors="replace")
        except OSError:
            return ""

    def has_bonus(self) -> bool:
        """Whether the repo contains bonus work (bonus files/directories or a `bonus` Makefile rule)."""
        if any("bonus" in part.lower() for p in self.files() for part in p.parts):
            return True
        return any(p.name == "Makefile" and re.search(r"^bonus\s*:", self.read(p), re.M) for p in self.files())
