"""A self-test of the build environment: which tools exist, and can it REALLY build and run things?

The same test runs inside the sandbox container and inside the terminal container (where claude works), so the answer is
about the environment itself, not about what an image recipe promises. A tool "being installed" is not enough: we compile
and run a C and a C++ program through make, and (on request) build and run a tiny Dockerfile on the separate daemon.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from shared.selftest.outcome import Runner
from shared.selftest.probes import HELLO_C, HELLO_CPP, HELLO_DOCKERFILE, HELLO_MAKEFILE, PROBES


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")[:120]


class SelfTest:
    """Template Method: look for the tools, then build and run a tiny project in a scratch folder (and Docker, when `deep`).
    `run(argv, cwd, timeout)` executes a command in the environment under test."""

    def __init__(self, run: Runner, scratch_parent: Path, *, deep: bool = False, extra: list[tuple[str, list[str], bool]] | None = None) -> None:
        self.run, self.parent, self.deep, self.extra = run, Path(scratch_parent), deep, extra or []
        self.results: list[dict] = []

    def record(self, name: str, ok: bool, detail: str, required: bool = True) -> None:
        self.results.append({"name": name, "ok": ok, "required": required, "detail": detail})

    def attempt(self, name: str, argv: list[str], cwd: Path, timeout: float, required: bool = True) -> bool:
        try:
            out = self.run(argv, cwd, timeout)
        except Exception as exc:  # the sandbox may be unreachable, a binary may be missing: report, never crash
            self.record(name, False, f"{type(exc).__name__}: {exc}"[:160], required)
            return False
        ok = out.rc == 0 and not out.timed_out
        self.record(name, ok, _first_line(out.stdout or out.stderr) if ok else (_first_line(out.stderr or out.stdout) or ("timed out" if out.timed_out else f"exit code {out.rc}")), required)
        return ok

    def execute(self) -> list[dict]:
        """[{"name", "ok", "required", "detail"}]"""
        self.parent.mkdir(parents=True, exist_ok=True)
        for name, argv, required in PROBES + self.extra:
            self.attempt(name, argv, self.parent, 20, required)
        # Really use them, in a scratch folder next to the real work.
        scratch = Path(tempfile.mkdtemp(prefix="selftest-", dir=self.parent))
        try:
            self._write_project(scratch)
            self._build_and_run(scratch)
            if self.deep:
                self._docker(scratch)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return self.results

    @staticmethod
    def _write_project(scratch: Path) -> None:
        (scratch / "hello_c.c").write_text(HELLO_C)
        (scratch / "hello_cpp.cpp").write_text(HELLO_CPP)
        (scratch / "Makefile").write_text(HELLO_MAKEFILE)
        (scratch / "Dockerfile").write_text(HELLO_DOCKERFILE)

    def _build_and_run(self, scratch: Path) -> None:
        if self.attempt("build C and C++ with make", ["make"], scratch, 60):
            self.attempt("run the C program", ["./c"], scratch, 20)
            self.attempt("run the C++ program", ["./cpp"], scratch, 20)

    def _docker(self, scratch: Path) -> None:
        if self.attempt("docker build a Dockerfile (needs internet)", ["docker", "build", "-q", "-t", "verdict-selftest", "."], scratch, 240):
            self.attempt("docker run the image", ["docker", "run", "--rm", "verdict-selftest"], scratch, 60)


def run_selftest(run: Runner, scratch_parent: Path, *, deep: bool = False, extra: list[tuple[str, list[str], bool]] | None = None) -> list[dict]:
    """The self-test as one call: [{"name", "ok", "required", "detail"}]."""
    return SelfTest(run, scratch_parent, deep=deep, extra=extra).execute()
