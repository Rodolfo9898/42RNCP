from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class ExecResult:
    rc: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.rc == 0 and not self.timed_out

    @property
    def output(self) -> str:
        return (self.stdout + ("\n" if self.stdout and self.stderr else "") + self.stderr).strip()

    @property
    def crashed(self) -> bool:
        """Killed by a signal (negative rc), e.g. SIGSEGV, SIGABRT, SIGBUS."""
        return self.rc < 0 and not self.timed_out


class SandboxError(RuntimeError):
    pass


class Sandbox:
    """Client for sandbox/runner.py. Everything run on behalf of a repo goes through here."""

    def __init__(self, url: str, env: dict[str, str] | None = None):
        self.url = url.rstrip("/")
        self.env = dict(env or {})          # added to every command this client runs (see sandbox/runner.py for what is accepted)

    def with_env(self, env: dict[str, str]) -> Sandbox:
        """The same sandbox, with extra variables for the commands run through the returned client."""
        return Sandbox(self.url, {**self.env, **env})

    @classmethod
    def from_env(cls) -> Sandbox | None:
        url = os.environ.get("SANDBOX_URL")
        return cls(url) if url else None

    def healthy(self) -> bool:
        try:
            with httpx.Client(trust_env=False, timeout=3) as client:
                return client.get(f"{self.url}/health").status_code == 200
        except httpx.HTTPError:
            return False

    def exec(self, argv: list[str], cwd: Path, timeout: float = 60, stdin: str = "") -> ExecResult:
        try:
            with httpx.Client(trust_env=False, timeout=timeout + 15) as client:   # an internal service: no proxies
                r = client.post(f"{self.url}/exec", json={"argv": argv, "cwd": str(cwd), "timeout": timeout, "stdin": stdin,
                                                           **({"env": self.env} if self.env else {})})
        except httpx.HTTPError as exc:
            raise SandboxError(f"sandbox unreachable: {exc}") from exc
        if r.status_code != 200:
            raise SandboxError(f"sandbox refused the command: {r.text}")
        return ExecResult(**r.json())


def sandbox_selftest(sandbox: Sandbox, workspace: Path, *, deep: bool = False) -> list[dict]:
    """The shared self-test, run inside the sandbox container through its runner."""
    from .selftest import Outcome, run_selftest

    def run(argv: list[str], cwd: Path, timeout: float) -> Outcome:
        res = sandbox.exec(argv, cwd, timeout=timeout)
        return Outcome(res.rc, res.stdout, res.stderr, res.timed_out)

    return run_selftest(run, workspace / "_selftest", deep=deep)
