"""src/scraper/site/login.py: the authenticator that refuses, the saved session, and signing in again."""
from __future__ import annotations

import pytest

from scraper.core.exceptions import ScraperError
from scraper.site.login import LOGIN_ON_YOUR_COMPUTER, RefusingAuthenticator, SessionManager
from tests.scraper.test_scraper import Buffer, FakeAuthenticator, FakeSite, settings

MESSAGE = "this process never logs in"


def test_the_refusing_authenticator_refuses_to_log_in_and_says_what_to_do_instead():
    refusing = RefusingAuthenticator(f"never here: {LOGIN_ON_YOUR_COMPUTER}")
    with pytest.raises(ScraperError, match="run `make samples-login` on your computer"):
        refusing.login("me", "secret")
    with pytest.raises(ScraperError, match="run `make samples-login` on your computer"):
        refusing.ask()


@pytest.mark.parametrize("with_credentials", [False, True])
def test_a_session_manager_with_the_refusing_authenticator_never_logs_in_with_or_without_credentials(tmp_path, with_credentials):
    site, refusing = FakeSite(), RefusingAuthenticator(MESSAGE)
    site.logged_in = False
    s = settings(tmp_path, **({} if with_credentials else {"login": None, "password": None}))
    s.state_file.parent.mkdir(parents=True), s.state_file.write_text("{}")                      # a saved session the intra no longer accepts
    reporter = Buffer()
    with pytest.raises(ScraperError, match=MESSAGE):
        SessionManager(s, refusing, reporter, site.http, refusing.ask).open()
    assert "Saved session not usable" in reporter.text
    assert site.requests == ["https://projects.intra.42.fr/projects/list?page=1", "https://signin.intra.42.fr/users/sign_in"]
    # (the one access check and the redirect it got: after the refusal nothing else was asked of the intra)


def test_without_a_saved_session_nothing_is_tried_and_the_refusal_comes_at_once(tmp_path):
    site, refusing = FakeSite(), RefusingAuthenticator(MESSAGE)
    with pytest.raises(ScraperError, match=MESSAGE):
        SessionManager(settings(tmp_path, login=None, password=None), refusing, Buffer(), site.http, refusing.ask).open()
    assert site.requests == []


def test_a_saved_session_is_either_missing_usable_or_turned_down(tmp_path):
    site = FakeSite()
    s = settings(tmp_path)
    manager = SessionManager(s, FakeAuthenticator(site), Buffer(), site.http)
    missing = manager.saved()
    assert (missing.found, missing.gateway, missing.reason) == (False, None, "") and site.requests == []
    s.state_file.parent.mkdir(parents=True), s.state_file.write_text("{}")
    usable = manager.saved()
    assert usable.found and usable.gateway is not None and usable.reason == ""
    site.logged_in = False
    turned_down = manager.saved()
    assert turned_down.found and turned_down.gateway is None and turned_down.reason == "not logged in (redirected to the sign-in page)"


def test_looking_at_the_saved_session_logs_nothing_and_asks_nobody(tmp_path):
    site, reporter, auth = FakeSite(), Buffer(), FakeAuthenticator(FakeSite())
    s = settings(tmp_path, login=None, password=None)
    s.state_file.parent.mkdir(parents=True), s.state_file.write_text("{}")
    SessionManager(s, auth, reporter, site.http, ask=lambda: pytest.fail("nobody should be asked")).saved()
    assert reporter.lines == [] and auth.calls == []


def test_signing_in_logs_in_again_even_if_the_saved_session_still_works(tmp_path):
    site, auth = FakeSite(), FakeAuthenticator(FakeSite())
    auth.site = site
    s = settings(tmp_path)
    s.state_file.parent.mkdir(parents=True), s.state_file.write_text("{}")
    manager = SessionManager(s, auth, Buffer(), site.http)
    assert manager.saved().gateway is not None
    manager.sign_in()
    assert auth.calls == [("tester", "pw")]
    manager.open()
    assert len(auth.calls) == 1                                                                 # (open() still reuses the saved session)


def test_signing_in_asks_for_the_credentials_it_does_not_have_and_checks_the_session_afterwards(tmp_path):
    site = FakeSite()
    site.logged_in = False
    auth = FakeAuthenticator(site)
    SessionManager(settings(tmp_path, login=None, password=None), auth, Buffer(), site.http, ask=lambda: ("typed", "secret")).sign_in()
    assert auth.calls == [("typed", "secret")]
    site.cloudflare = True
    with pytest.raises(ScraperError, match="plain HTTP can't read the intra: blocked by a Cloudflare challenge"):
        SessionManager(settings(tmp_path), auth, Buffer(), site.http).sign_in()
