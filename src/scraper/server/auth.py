"""Who may call the service: the web app, which shares the token."""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException


class TokenGuard:
    """FastAPI dependency for every route but /health: the shared secret must come in the `x-scraper-token` header. No token
    configured: nothing is allowed."""

    def __init__(self, expected: str) -> None:
        self._expected = expected.encode()

    def __call__(self, x_scraper_token: str | None = Header(default=None)) -> None:
        if not self._expected or not x_scraper_token or not hmac.compare_digest(x_scraper_token.encode(), self._expected):
            raise HTTPException(401, "bad token")
