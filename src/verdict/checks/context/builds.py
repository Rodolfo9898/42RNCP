"""Building and running the project in the sandbox."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from verdict.checks.context.build_result import BuildResult
from verdict.checks.context.layout import Layout
from verdict.checks.context.memo import memo
from verdict.checks.context.offline import NOTES_KEY, offline_reason
from verdict.gateways.sandbox import ExecResult, Sandbox, SandboxError

EXEC_MAGIC = (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")  # ELF; Mach-O (for local dev)
LIBRARY_SUFFIXES = frozenset({".a", ".so", ".dylib"})
NOT_RUNNABLE_SUFFIXES = frozenset({".o", *LIBRARY_SUFFIXES})
# What a build prints when it tried to download something (git submodule update, curl, wget, pip...) and could not.
NETWORK_ERROR = re.compile(r"Could not resolve host|Temporary failure in name resolution|Name or service not known|Network is unreachable|"
                           r"Failed to connect to|Connection (?:refused|timed out)|unable to access '?https?://|Could not read from remote repository", re.I)


class Builds:
    """Runs commands in the sandbox, in the folder of a unit, and builds each unit once (the result is kept in the review's cache);
    knows what a build leaves behind: the programs and the libraries."""

    def __init__(self, repo: Path, sandbox: Sandbox | None, layout: Layout, cache: dict[str, Any]) -> None:
        self.repo, self.sandbox, self.layout, self.cache = repo, sandbox, layout, cache

    def run(self, argv: list[str], unit: str = ".", timeout: float = 60, stdin: str = "") -> ExecResult:
        if self.sandbox is None:
            raise SandboxError("no sandbox configured")
        return self.sandbox.exec(argv, self.layout.unit_dir(unit), timeout=timeout, stdin=stdin)

    def build(self, unit: str, bonus: bool = False) -> BuildResult:
        return memo(self.cache, f"build:{unit}:{bonus}", lambda: self._build(unit, bonus))

    def _build(self, unit: str, bonus: bool) -> BuildResult:
        if not self.layout.has_makefile(unit):
            return BuildResult(False, f"No Makefile in {unit}/", ran=False)
        res = self.run(["make", "bonus"] if bonus else ["make"], unit, timeout=240)
        log = res.output + ("\n[timed out]" if res.timed_out else "")
        return BuildResult(res.ok, log, needs_network=not res.ok and bool(NETWORK_ERROR.search(res.output)))

    def offline_reason(self, build: BuildResult) -> str:
        return offline_reason(self.repo, self.cache.get(NOTES_KEY, []), build)

    def executables(self, unit: str) -> list[Path]:
        """Programs that can be run. Object files and shared libraries are ELF as well, so the magic number is not enough."""
        base = self.layout.unit_dir(unit)
        if not base.is_dir():
            return []
        return sorted(p for p in self._built_files(base) if p.suffix not in NOT_RUNNABLE_SUFFIXES
                      and p.stat().st_mode & 0o111 and self._is_elf(p))

    def libraries(self, unit: str) -> list[Path]:
        base = self.layout.unit_dir(unit)
        if not base.is_dir():
            return []
        return sorted(p for p in self._built_files(base) if p.suffix in LIBRARY_SUFFIXES)

    @staticmethod
    def _built_files(base: Path) -> list[Path]:
        return [p for p in base.iterdir() if p.is_file() and not p.is_symlink()]

    @staticmethod
    def _is_elf(path: Path) -> bool:
        try:
            with path.open("rb") as fh:
                return fh.read(4) in EXEC_MAGIC
        except OSError:
            return False
