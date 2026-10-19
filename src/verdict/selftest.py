"""A self-test of the build environment: which tools exist, and can it REALLY build and run things?

The same test runs inside the sandbox container and inside the terminal container (where claude works), so the answer is
about the environment itself, not about what an image recipe promises. A tool "being installed" is not enough: we compile
and run a C and a C++ program through make, and (on request) build and run a tiny Dockerfile on the separate daemon.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Outcome:
    rc: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


Runner = Callable[[list[str], Path, float], Outcome]

# (name, command, required). "required" tools decide whether the environment is "ready".
PROBES = [
    ("C compiler (cc)", ["cc", "--version"], True),
    ("C++ compiler (c++)", ["c++", "--version"], True),
    ("make", ["make", "--version"], True),
    ("docker client", ["docker", "--version"], True),
    ("docker compose", ["docker", "compose", "version"], True),
    ("docker daemon", ["docker", "info", "--format", "{{.ServerVersion}}"], True),
    ("valgrind", ["valgrind", "--version"], False),
    ("norminette", ["norminette", "--version"], False),
]

HELLO_C = '#include <stdio.h>\nint main(void) { puts("hello from C"); return 0; }\n'
HELLO_CPP = '#include <iostream>\nint main() { std::cout << "hello from C++\\n"; return 0; }\n'
HELLO_MAKEFILE = (
    "all: c cpp\n"
    "c: hello_c.c\n\tcc -Wall -Wextra -Werror hello_c.c -o c\n"
    "cpp: hello_cpp.cpp\n\tc++ -Wall -Wextra -Werror -std=c++98 hello_cpp.cpp -o cpp\n"
)
HELLO_DOCKERFILE = 'FROM busybox\nRUN echo built-inside-docker > /proof\nCMD ["cat", "/proof"]\n'


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")[:120]


def run_selftest(run: Runner, scratch_parent: Path, *, deep: bool = False, extra: list[tuple[str, list[str], bool]] | None = None) -> list[dict]:
    """[{"name", "ok", "required", "detail"}]. `run(argv, cwd, timeout)` executes a command in the environment under test."""
    results: list[dict] = []

    def record(name: str, ok: bool, detail: str, required: bool = True) -> None:
        results.append({"name": name, "ok": ok, "required": required, "detail": detail})

    def attempt(name: str, argv: list[str], cwd: Path, timeout: float, required: bool = True) -> bool:
        try:
            out = run(argv, cwd, timeout)
        except Exception as exc:  # the sandbox may be unreachable, a binary may be missing: report, never crash
            record(name, False, f"{type(exc).__name__}: {exc}"[:160], required)
            return False
        ok = out.rc == 0 and not out.timed_out
        record(name, ok, _first_line(out.stdout or out.stderr) if ok else (_first_line(out.stderr or out.stdout) or ("timed out" if out.timed_out else f"exit code {out.rc}")), required)
        return ok

    parent = Path(scratch_parent)
    parent.mkdir(parents=True, exist_ok=True)
    for name, argv, required in PROBES + (extra or []):
        attempt(name, argv, parent, 20, required)

    # Really use them, in a scratch folder next to the real work.
    scratch = Path(tempfile.mkdtemp(prefix="selftest-", dir=parent))
    try:
        (scratch / "hello_c.c").write_text(HELLO_C)
        (scratch / "hello_cpp.cpp").write_text(HELLO_CPP)
        (scratch / "Makefile").write_text(HELLO_MAKEFILE)
        (scratch / "Dockerfile").write_text(HELLO_DOCKERFILE)
        if attempt("build C and C++ with make", ["make"], scratch, 60):
            attempt("run the C program", ["./c"], scratch, 20)
            attempt("run the C++ program", ["./cpp"], scratch, 20)
        if deep:
            if attempt("docker build a Dockerfile (needs internet)", ["docker", "build", "-q", "-t", "verdict-selftest", "."], scratch, 240):
                attempt("docker run the image", ["docker", "run", "--rm", "verdict-selftest"], scratch, 60)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return results


def summarize(results: list[dict]) -> dict:
    failed = [r["name"] for r in results if not r["ok"] and r["required"]]
    docker_down = "docker daemon" in failed
    basics = [n for n in failed if not n.startswith("docker")]
    return {
        "ready": not failed,
        "failed": failed,
        "basics_ok": not basics,
        "docker_ok": not [n for n in failed if n.startswith("docker")],
        "docker_daemon_down": docker_down and "docker client" not in failed,
    }
