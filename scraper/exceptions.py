"""Errors the user should see as a plain message (not a traceback)."""
from __future__ import annotations


class ScraperError(Exception):
    """An expected failure: the message is printed and the program exits."""


class SessionExpired(ScraperError):
    """The intra redirected us to the sign-in page."""

    def __init__(self, message: str = "\nThe session expired. Run it again: it logs in again and skips what you already have.") -> None:
        super().__init__(message)


class LoginError(ScraperError):
    """The browser login did not complete."""
