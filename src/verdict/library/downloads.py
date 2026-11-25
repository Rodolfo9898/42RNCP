"""Downloading the subjects the library lacks from the 42 intra, and filing them in the folders of their series."""

from __future__ import annotations


class SubjectDownloads:
    """What the editor may ask of the subject downloader, between the routes and the scraper gateway (which only carries requests).

    The library is not told about a finished download or a reorganization: its listing reads the folders each time, so what the
    downloader put there is in the next `GET /api/library`."""

    def __init__(self, scraper) -> None:
        self.scraper = scraper

    def plan(self, tracks: list[str], children: bool) -> dict:
        """What the library lacks, with `ready`: the saved intra session is usable, so a download can start (the editor enables the
        button from it, and shows the reason from `session` when it is not)."""
        answer = self.scraper.plan(tracks, children)
        session = answer.get("session")
        return {**answer, "ready": isinstance(session, dict) and session.get("valid") is True}

    def start(self, *, tracks: list[str] | None, projects: list[str] | None, artifacts: bool, children: bool, force: bool) -> dict:
        return self.scraper.start_download(tracks=tracks, projects=projects, artifacts=artifacts, children=children, force=force)

    def current(self, since: int) -> dict:
        return self.scraper.current_download(since)

    def cancel(self) -> dict:
        return self.scraper.cancel_download()

    def reorganize(self, dry_run: bool) -> dict:
        return self.scraper.reorganize(dry_run)
