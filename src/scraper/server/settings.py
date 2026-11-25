"""Everything the scraper service reads from its environment, read once at start and handed to whoever needs it."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from scraper.core.config import Settings
from scraper.core.exceptions import ScraperError


@dataclass(frozen=True)
class ServiceSettings:
    """The scraper's own Settings (SAMPLES_DIR, ARTIFACTS_DIR, SESSION_DIR, SCRAPE_DELAY, SUBJECT_LANG) and the token shared with the web app."""

    token: str
    scraper: Settings

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> ServiceSettings:
        token = environ.get("SCRAPER_TOKEN", "")
        if not token:
            raise ScraperError("SCRAPER_TOKEN is not set: the scraper service shares it with the web app and will not start without it.")
        # The service never holds the intra login (it could not use it: it has no browser), even if the environment happens to have it.
        return cls(token, replace(Settings.from_env(environ=environ), login=None, password=None))
