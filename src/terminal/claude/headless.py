"""The one-click review: `claude -p`, read-only tools, on a sanitized copy of the repository."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from terminal.claude.command import ClaudeCommand
from terminal.environment.child import ChildEnvironment
from terminal.projects.folders import ProjectFolders
from terminal.projects.sanitizer import SanitizedCopy

MAX_STDOUT = 2_000_000
MAX_STDERR = 4000


class ReviewFailed(Exception):
    """A review that did not produce an answer: `status` is the HTTP status that says why (400 bad request, 499 the app gave up, 504 too slow)."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


class HeadlessReview:
    """Runs one headless claude at a time (Facade: copy, run, wait, clean up). Bounded by a deadline, and by the app: when it gives up
    (the user pressed Stop) claude is killed."""

    def __init__(self, command: ClaudeCommand, environment: ChildEnvironment, projects: ProjectFolders, copies: SanitizedCopy,
                 default_timeout: float) -> None:
        self.command, self.environment, self.projects, self.copies = command, environment, projects, copies
        self.default_timeout = default_timeout
        self._one_at_a_time = asyncio.Semaphore(1)

    async def run(self, body: dict, disconnected: Callable[[], Awaitable[bool]]) -> dict:
        """body: {"repo": <folder in the projects>, "prompt", "schema", "model"?, "timeout"?}. -> {"returncode", "stdout", "stderr"}"""
        if not isinstance(body, dict):
            raise ReviewFailed(400, "the body must be a JSON object")
        try:
            source = self.projects.resolve(str(body.get("repo", "")))
            argv = self.command.review(str(body["prompt"]), dict(body["schema"]), body.get("model") or None)
            timeout = float(body.get("timeout", self.default_timeout))
        except (ValueError, KeyError, TypeError) as exc:
            raise ReviewFailed(400, str(exc)) from exc
        async with self._one_at_a_time:
            try:
                workdir = await asyncio.get_running_loop().run_in_executor(None, self.copies.make, source)
            except (ValueError, OSError) as exc:
                raise ReviewFailed(400, str(exc)) from exc
            try:
                return await self._ask(argv, workdir, timeout, disconnected)
            finally:
                self.copies.cleanup(workdir)

    async def _ask(self, argv: list[str], workdir: Path, timeout: float, disconnected: Callable[[], Awaitable[bool]]) -> dict:
        process = await asyncio.create_subprocess_exec(
            *argv, cwd=workdir, env=self.environment.build(),
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await self._finish(process, timeout, disconnected)
            return {
                "returncode": process.returncode,
                "stdout": stdout[:MAX_STDOUT].decode("utf-8", errors="replace"),
                "stderr": stderr[-MAX_STDERR:].decode("utf-8", errors="replace"),
            }
        finally:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass

    @staticmethod
    async def _finish(process: asyncio.subprocess.Process, timeout: float, disconnected: Callable[[], Awaitable[bool]]) -> tuple[bytes, bytes]:
        communicate = asyncio.ensure_future(process.communicate())
        deadline = time.monotonic() + timeout
        while not communicate.done():
            if await disconnected():           # the app gave up (user pressed Stop)
                raise ReviewFailed(499, "client disconnected")
            if time.monotonic() > deadline:
                raise ReviewFailed(504, "claude did not finish in time")
            await asyncio.wait({communicate}, timeout=1)
        return communicate.result()
