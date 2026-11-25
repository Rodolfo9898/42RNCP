"""--login: the browser login on its own, so that the editor's downloader has a session to use."""
from __future__ import annotations

from scraper.cli.commands import Command
from scraper.core.config import ROOT, Settings
from scraper.core.reporting import Reporter
from scraper.site.login import SessionManager


class LoginCommand(Command):
    """Logs in with the browser (INTRA_LOGIN and INTRA_PASSWORD from .env, else asked; --headed for 2FA), checks that plain HTTP can
    read the intra with what was saved, and says where it is. The downloader service reads that session and never logs in itself."""

    def __init__(self, session: SessionManager, settings: Settings, reporter: Reporter) -> None:
        self.session, self.settings, self.reporter = session, settings, reporter

    def execute(self) -> None:
        self.session.sign_in()
        self.reporter.log(f"Session saved in {self._where()}. Start (or restart) the editor with `make run`")

    def _where(self) -> str:
        folder = self.settings.session_dir
        return f"{folder.relative_to(ROOT).as_posix() if folder.is_relative_to(ROOT) else folder}/"
