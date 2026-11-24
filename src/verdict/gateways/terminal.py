"""The terminal service, seen from the web app: claude's saved report, the subject PDFs it holds, and its environment check.

Gateway pattern: the only place that knows the service's addresses, its token, and that it is an internal service (no proxy variables
are honoured). `NullTerminal` is the same interface for a deployment without a terminal (Null Object): nothing found, nothing to do.
"""

from __future__ import annotations

from typing import Any

import httpx

from verdict.core.errors import Unavailable

NO_REPORT = {"found": False, "text": "", "name": ""}


class NullTerminal:
    configured = False

    def report(self, session_id: str) -> dict:
        return dict(NO_REPORT)

    def delete_report(self, session_id: str) -> bool:
        return False

    def subject_digests(self, session_id: str) -> dict[str, str]:
        return {}

    def put_subjects(self, session_id: str, files: dict[str, bytes]) -> None:
        return None

    def environment(self, deep: bool = False) -> dict:
        raise Unavailable("the terminal is not configured")


class TerminalGateway(NullTerminal):
    configured = True

    def __init__(self, url: str, token: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self.url, self.token, self.transport = url.rstrip("/"), token, transport

    def _call(self, method: str, path: str, *, timeout: float = 5, **kwargs: Any) -> httpx.Response:
        with httpx.Client(trust_env=False, timeout=timeout, transport=self.transport) as client:      # an internal service: no proxies
            response = client.request(method, f"{self.url}{path}", headers={"x-terminal-token": self.token}, **kwargs)
        response.raise_for_status()
        return response

    def report(self, session_id: str) -> dict:
        """What claude saved for this review: {"found", "text", "name"}. Raises when the service cannot be reached."""
        return self._call("GET", f"/sessions/{session_id}/report").json()

    def delete_report(self, session_id: str) -> bool:
        """A new run starts without the last report. Best effort: an unreachable service must not stop a run."""
        try:
            return bool(self._call("DELETE", f"/sessions/{session_id}/report").json().get("deleted"))
        except (httpx.HTTPError, ValueError):
            return False

    def subject_digests(self, session_id: str) -> dict[str, str]:
        return self._call("GET", f"/sessions/{session_id}/subjects").json().get("files") or {}

    def put_subjects(self, session_id: str, files: dict[str, bytes]) -> None:
        """Replace the review's PDFs in the terminal with exactly these."""
        parts = [("files", (name, data, "application/pdf")) for name, data in files.items()]
        self._call("PUT", f"/sessions/{session_id}/subjects", timeout=60, files=parts)

    def environment(self, deep: bool = False) -> dict:
        """The tools claude's terminal has: {"tools": [...]}. The deep check builds a Dockerfile, so it may take minutes."""
        try:
            return self._call("GET", "/environment", timeout=360 if deep else 90, params={"deep": deep}).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise Unavailable(f"could not reach the terminal service ({type(exc).__name__})") from exc
