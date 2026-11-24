"""The environment claude works in, tested for real."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from shared.selftest import Outcome, run_selftest
from terminal.environment.child import ChildEnvironment

Probe = tuple[str, list[str], bool]       # (name, command, required)


class EnvironmentSelfTest:
    """Runs the shared self-test (compilers, make, docker client and daemon, a real build) inside this container, with claude's own
    environment, plus the probes only this container has (`extra`: claude itself, a debugger). (Adapter: the shared test only knows
    a `run(argv, cwd, timeout)`; this is how this container runs one.)"""

    def __init__(self, environment: ChildEnvironment, scratch: Path, extra: list[Probe]) -> None:
        self.environment, self.scratch, self.extra = environment, scratch, extra

    async def run(self, deep: bool = False) -> list[dict]:
        self.scratch.mkdir(parents=True, exist_ok=True)
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: run_selftest(self._execute, self.scratch, deep=deep, extra=self.extra))

    def _execute(self, argv: list[str], cwd: Path, timeout: float) -> Outcome:
        try:
            done = subprocess.run(argv, cwd=cwd, env=self.environment.build(), capture_output=True, text=True, timeout=timeout,
                                  stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return Outcome(-1, timed_out=True)
        except OSError as exc:
            return Outcome(127, stderr=str(exc))
        return Outcome(done.returncode, done.stdout[-4000:], done.stderr[-4000:])
