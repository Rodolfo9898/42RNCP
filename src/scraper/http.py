"""HTTP client carrying the cookies and user-agent of the logged-in browser (httpx: the same library as the rest of the project)."""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class HttpClient:
    TIMEOUT = httpx.Timeout(60.0, connect=10.0)
    RETRIES = 4

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, *, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.sleep = sleep
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                     "Accept-Language": "en-US,en;q=0.9"},
            follow_redirects=True, timeout=self.TIMEOUT, transport=transport)

    @classmethod
    def from_saved_session(cls, state_file: Path, user_agent_file: Path, **kwargs) -> HttpClient:
        """A client with the cookies and user-agent the browser login saved (if any)."""
        user_agent = user_agent_file.read_text().strip() if user_agent_file.exists() else DEFAULT_USER_AGENT
        client = cls(user_agent, **kwargs)
        if state_file.exists():
            client.load_cookies(state_file)
        return client

    def load_cookies(self, state_file: Path) -> None:
        """Load the cookies of a Playwright storage_state file (the expired ones are left out)."""
        now = time.time()
        for c in json.loads(state_file.read_text()).get("cookies", []):
            if 0 < c.get("expires", -1) < now:
                continue
            self.client.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))

    def _wait(self, attempt: int, response: httpx.Response | None) -> None:
        retry_after = response.headers.get("Retry-After", "") if response is not None else ""
        self.sleep(min(float(retry_after), 60.0) if retry_after.replace(".", "", 1).isdigit() else 2.0 ** attempt)

    def get(self, url: str, **kwargs) -> httpx.Response:
        """GET with a few retries on a busy or failing server (429, 5xx) and on network errors."""
        for attempt in range(self.RETRIES + 1):
            try:
                response = self.client.get(url, **kwargs)
            except httpx.TransportError:
                if attempt == self.RETRIES:
                    raise
                self._wait(attempt, None)
                continue
            if response.status_code in RETRY_STATUSES and attempt < self.RETRIES:
                self._wait(attempt, response)
                continue
            return response
        raise AssertionError("unreachable")

    @contextmanager
    def stream(self, url: str) -> Iterator[httpx.Response]:
        with self.client.stream("GET", url) as response:
            yield response
