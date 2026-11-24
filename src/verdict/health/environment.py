"""Can the sandbox AND claude's terminal really build and run things? C, C++, make, docker (client and daemon)."""

from __future__ import annotations

import time
from pathlib import Path

from shared.selftest import summarize
from verdict.core.errors import Unavailable
from verdict.gateways.sandbox import SandboxError, sandbox_selftest

CACHE_SECONDS = 20


class EnvironmentService:
    """`deep` also builds and runs a tiny Dockerfile on the separate daemon (needs internet, so only on request)."""

    def __init__(self, sandbox, terminal, workspace: Path) -> None:
        self.sandbox, self.terminal, self.workspace = sandbox, terminal, workspace
        self._cache: dict[bool, tuple[float, dict]] = {}

    def check(self, deep: bool = False) -> dict:
        now = time.monotonic()
        cached = self._cache.get(deep)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]
        parts = {"sandbox": self._sandbox(deep), "terminal": self._terminal(deep)}
        answer = {**parts, "ready": all(p["available"] and p["summary"]["ready"] for p in parts.values()), "deep": deep}
        self._cache[deep] = (now, answer)
        return answer

    def _sandbox(self, deep: bool) -> dict:
        if self.sandbox is None:
            return self._missing("the sandbox is not configured")
        try:
            tools = sandbox_selftest(self.sandbox, self.workspace, deep=deep)
        except (SandboxError, OSError) as exc:
            return self._missing(str(exc))
        return {"available": True, "tools": tools, "summary": summarize(tools)}

    def _terminal(self, deep: bool) -> dict:
        try:
            tools = self.terminal.environment(deep)["tools"]
        except Unavailable as exc:
            return self._missing(exc.message)
        return {"available": True, "tools": tools, "summary": summarize(tools)}

    @staticmethod
    def _missing(error: str) -> dict:
        return {"available": False, "tools": [], "summary": summarize([]), "error": error}
