"""Running one command: its own process group, limits, a timeout, and bounded output."""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass

from sandbox.execution.environment import CommandEnvironment
from sandbox.execution.limits import ResourceLimits
from sandbox.request.validator import ExecRequest


@dataclass(frozen=True)
class ExecResult:
    rc: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool

    @classmethod
    def not_started(cls, error: OSError) -> ExecResult:
        """The command could not even start (e.g. the executable was not found): the shell's own code for that."""
        return cls(127, "", str(error), False, False)

    def as_dict(self) -> dict:
        return {"rc": self.rc, "stdout": self.stdout, "stderr": self.stderr, "timed_out": self.timed_out, "truncated": self.truncated}


class CommandRunner:
    """Runs the commands of validated requests, one process group each, so a timeout kills everything the command started."""

    def __init__(self, environment: CommandEnvironment, limits: ResourceLimits, max_output: int = 1_000_000) -> None:
        self.environment, self.limits, self.max_output = environment, limits, max_output      # max_output: bytes kept per stream

    def run(self, request: ExecRequest) -> ExecResult:
        proc = subprocess.Popen(
            request.argv,
            cwd=request.cwd,
            env=self.environment.build(request.env),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            preexec_fn=self.limits.apply,
        )
        timed_out = False
        try:
            out, err = proc.communicate(request.stdin.encode(), timeout=request.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc.pid)
            out, err = proc.communicate()
        finally:
            self._kill_group(proc.pid)  # reap anything the command left behind
        return ExecResult(
            proc.returncode,
            out[:self.max_output].decode(errors="replace"),
            err[:self.max_output].decode(errors="replace"),
            timed_out,
            len(out) > self.max_output or len(err) > self.max_output,
        )

    @staticmethod
    def _kill_group(pgid: int) -> None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass  # already gone (macOS reports EPERM for a group that only holds zombies)
