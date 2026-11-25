"""The subject downloader (the scraper service), seen from the web app: what the library lacks, a download that runs in the background,
and the filing of the PDFs into the folders of their series.

Gateway pattern: the only place that knows the service's addresses, its token, and that it is an internal service (no proxy variables
are honoured, no redirect is followed with the token). `NullScraper` is the same interface for a deployment without a scraper
(Null Object): every call says the downloader is not configured. Every failure leaves here as a `VerdictError` with a message for the
person, never as an `httpx` exception, and the token is never part of a message.
"""

from __future__ import annotations

from typing import Any

import httpx

from verdict.core.errors import Conflict, Failed, Unavailable, VerdictError

NOT_CONFIGURED = "the subject downloader is not configured"
UNREACHABLE = "could not reach the subject downloader (is the scraper service running?)"
UNREADABLE = "the subject downloader answered something this app cannot read"
TOKEN_REFUSED = "the subject downloader refused this app's token (SCRAPER_TOKEN must be the same in the web and scraper services)"
CANNOT_REACH = (httpx.RequestError, httpx.InvalidURL)          # connecting, timeouts, protocol errors, an address that is no address
ACTIONABLE = {400: VerdictError, 409: Conflict}                # a refusal the person can act on: the service's own words go through
GATEWAY_STATUSES = {502, 503, 504}


class NullScraper:
    """The calls are defined once, over `_call`; without a scraper, `_call` is where the answer is that there is none."""

    configured = False

    def plan(self, tracks: list[str], children: bool) -> dict:
        """What each track lacks, and whether the saved intra session can download it. No track: all three."""
        params = [*(("track", track) for track in tracks), ("children", children)]
        return self._call("GET", "/plan", timeout=45, params=params)         # (it checks the session against the intra)

    def start_download(self, *, tracks: list[str] | None, projects: list[str] | None, artifacts: bool, children: bool, force: bool) -> dict:
        selection = {"tracks": tracks, "projects": projects, "artifacts": artifacts, "children": children, "force": force}
        return self._call("POST", "/downloads", timeout=45, json=selection)

    def current_download(self, since: int = 0) -> dict:
        """The state of the download, and its log lines from number `since` on."""
        return self._call("GET", "/downloads/current", timeout=10, params={"since": since})

    def cancel_download(self) -> dict:
        return self._call("DELETE", "/downloads/current", timeout=10)

    def reorganize(self, dry_run: bool) -> dict:
        """File the PDFs and artifacts that are already there into the folders of their series (or only list the moves)."""
        return self._call("POST", "/reorganizations", timeout=60, json={"dry_run": dry_run})

    def _call(self, method: str, path: str, *, timeout: float, **kwargs: Any) -> dict:
        raise Unavailable(NOT_CONFIGURED)


class ScraperGateway(NullScraper):
    configured = True

    def __init__(self, url: str, token: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self.url, self.token, self.transport = url.rstrip("/"), token, transport

    def _call(self, method: str, path: str, *, timeout: float, **kwargs: Any) -> dict:
        try:
            with httpx.Client(trust_env=False, timeout=timeout, transport=self.transport) as client:      # an internal service: no proxies
                response = client.request(method, f"{self.url}{path}", headers={"x-scraper-token": self.token}, **kwargs)
        except CANNOT_REACH as exc:
            raise Unavailable(UNREACHABLE) from exc
        return self._answer(response)

    @classmethod
    def _answer(cls, response: httpx.Response) -> dict:
        body = cls._object(response)
        if response.is_success:
            if body is None:
                raise Failed(UNREADABLE)
            return body
        detail = (body or {}).get("detail")
        message = detail if isinstance(detail, str) and detail else f"the subject downloader answered HTTP {response.status_code}"
        raise cls._refusal(response.status_code, message)

    @staticmethod
    def _object(response: httpx.Response) -> dict | None:
        """The JSON object the service answered, or None when it answered anything else."""
        try:
            body = response.json()
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    @staticmethod
    def _refusal(status: int, message: str) -> VerdictError:
        if status in ACTIONABLE:
            return ACTIONABLE[status](message)
        if status in (401, 403):
            return Unavailable(TOKEN_REFUSED)
        return (Unavailable if status in GATEWAY_STATUSES else Failed)(message)
