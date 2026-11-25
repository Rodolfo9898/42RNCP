"""The saved session, as the service uses it: read, never made. (The login happens on the person's computer, `make samples-login`.)"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from scraper.core.config import Settings
from scraper.core.reporting import NullReporter, Reporter
from scraper.core.utils import first_line
from scraper.site.http import HttpClient
from scraper.site.login import LOGIN_ON_YOUR_COMPUTER, RefusingAuthenticator, SessionManager

NO_SESSION = f"no saved session: {LOGIN_ON_YOUR_COMPUTER}"
REFUSAL = f"The downloader never logs in to the 42 intra: {LOGIN_ON_YOUR_COMPUTER}, then try again."


@dataclass(frozen=True)
class SessionStatus:
    valid: bool
    reason: str = ""

    def advice(self) -> str:
        """What to tell someone who wanted to download with a session that does not work."""
        return self.reason if self.reason == NO_SESSION else f"the saved session is not usable ({self.reason}): {LOGIN_ON_YOUR_COMPUTER}"


class SavedSessions:
    """Factory of the service's SessionManagers (their authenticator refuses to log in); it also tells whether the saved session works."""

    def __init__(self, settings: Settings, http_factory: Callable[[], HttpClient] | None = None) -> None:
        self.settings, self.http_factory = settings, http_factory

    def manager(self, reporter: Reporter) -> SessionManager:
        refusing = RefusingAuthenticator(REFUSAL)
        return SessionManager(self.settings, refusing, reporter, self.http_factory, refusing.ask)

    def status(self) -> SessionStatus:
        """The same access check a download starts with. Whatever goes wrong with it is a reason, not an error."""
        try:
            saved = self.manager(NullReporter()).saved()
        except httpx.HTTPError as exc:
            return SessionStatus(False, f"could not reach the 42 intra ({first_line(exc)})")
        except (OSError, ValueError, KeyError) as exc:
            return SessionStatus(False, f"the saved session could not be read ({first_line(exc)})")
        if saved.gateway is not None:
            return SessionStatus(True)
        return SessionStatus(False, saved.reason if saved.found else NO_SESSION)
