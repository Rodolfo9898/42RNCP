"""Logging in (Playwright is used here and nowhere else) and keeping a usable session."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from .config import Settings
from .exceptions import LoginError, ScraperError
from .http import HttpClient
from .intra import PROJECTS_URL, SIGNIN_URL, IntraGateway, on_intra
from .reporting import Reporter
from .utils import first_line


class Authenticator(ABC):
    @abstractmethod
    def login(self, login: str, password: str) -> None:
        """Log in and save the session (cookies + user-agent) where the HTTP client finds it."""


class BrowserAuthenticator(Authenticator):
    """A real browser logs in (it copes with the SSO redirects and 2FA); we keep its cookies."""

    USER_SEL = 'input[name="username"], input#username, input[name="user[login]"], input#user_login'
    PASS_SEL = 'input[name="password"], input#password, input[name="user[password]"], input#user_password'

    def __init__(self, settings: Settings, reporter: Reporter) -> None:
        self.settings, self.reporter = settings, reporter

    def login(self, login: str, password: str) -> None:
        try:
            from playwright.sync_api import TimeoutError as PWTimeout
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ScraperError("The login needs Playwright. Use `make samples` (it installs it), or `pip install playwright`.") from None

        s = self.settings
        self.reporter.log("Logging in with the browser...")
        with sync_playwright() as pw:
            browser = self._launch(pw)
            try:
                ctx = browser.new_context()
                page = ctx.new_page()
                page.set_default_timeout(30_000)
                page.goto(SIGNIN_URL, wait_until="domcontentloaded")
                page.wait_for_selector(self.USER_SEL, timeout=20_000)
                page.fill(self.USER_SEL, login)
                page.fill(self.PASS_SEL, password)
                page.press(self.PASS_SEL, "Enter")
                # Headed mode: leave time for 2FA / captcha to be completed by hand.
                try:
                    page.wait_for_url(on_intra, timeout=30_000 if s.headless else 180_000)
                except PWTimeout:
                    err = page.locator(".alert, .kc-feedback-text, #input-error, .error").first
                    detail = err.inner_text().strip() if err.count() else "no error message found on the page"
                    hint = " Run it again with --headed to complete 2FA/captcha by hand." if s.headless else ""
                    raise LoginError(f"Login did not complete ({detail}).{hint}") from None
                page.goto(f"{PROJECTS_URL}/", wait_until="load")      # so the projects site's cookie is in the saved state
                if not on_intra(page.url):
                    raise LoginError("Logged in, but could not open projects.intra.42.fr")
                s.state_file.parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=str(s.state_file))
                s.state_file.chmod(0o600)
                # Cloudflare ties its clearance cookie to the user-agent, so reuse the exact same one.
                s.user_agent_file.write_text(page.evaluate("navigator.userAgent"))
            finally:
                browser.close()
        self.reporter.log("Logged in, session saved.")

    def _launch(self, pw):
        """Prefer the Chrome already installed on the machine; fall back to Playwright's Chromium."""
        channel, headless = self.settings.browser_channel, self.settings.headless
        if channel and channel != "chromium":
            try:
                return pw.chromium.launch(channel=channel, headless=headless)
            except Exception as exc:
                self.reporter.log(f"Could not launch '{channel}' ({first_line(exc)}); trying bundled Chromium")
        return pw.chromium.launch(headless=headless)


class SessionManager:
    """A logged-in IntraGateway: the saved session if it still works, else a new login."""

    def __init__(self, settings: Settings, authenticator: Authenticator, reporter: Reporter,
                 http_factory: Callable[[], HttpClient] | None = None,
                 ask: Callable[[], tuple[str, str]] | None = None) -> None:
        self.settings, self.authenticator, self.reporter = settings, authenticator, reporter
        self.ask = ask or self._cannot_ask
        self._new_http = http_factory or (lambda: HttpClient.from_saved_session(settings.state_file, settings.user_agent_file))

    @staticmethod
    def _cannot_ask() -> tuple[str, str]:
        raise ScraperError("Not logged in: set INTRA_LOGIN and INTRA_PASSWORD in .env (or in the environment) and run it again.")

    def open(self) -> IntraGateway:
        s = self.settings
        if s.state_file.exists():
            gateway = IntraGateway(self._new_http())
            reason = gateway.check_access()
            if reason is None:
                self.reporter.log("Reusing saved session.")
                return gateway
            self.reporter.log(f"Saved session not usable: {reason}")
        login, password = (s.login, s.password) if s.login and s.password else self.ask()
        self.authenticator.login(login, password)
        gateway = IntraGateway(self._new_http())
        reason = gateway.check_access()
        if reason is not None:
            extra = ""
            if "Cloudflare" in reason:
                extra = ("\nPlain HTTP requests are being challenged even with the browser's cookies and user-agent: "
                         "the page fetching would have to run inside the browser.")
            raise ScraperError(f"Logged in with the browser, but plain HTTP can't read the intra: {reason}.{extra}")
        return gateway
