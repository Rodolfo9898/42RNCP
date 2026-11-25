"""--login: the browser login on its own (src/scraper/cli/login.py), built by the CommandFactory, run with a fake authenticator."""
from __future__ import annotations

import pytest

from scraper.cli.login import LoginCommand
from scraper.cli.main import main
from scraper.cli.parser import CommandFactory, build_parser
from scraper.core.config import ROOT, Settings
from scraper.site.login import Authenticator
from tests.scraper.test_scraper import Buffer, FakeAuthenticator, FakeSite, settings

FINAL = "Start (or restart) the editor with `make run`"


def login_with(tmp_path, site, **overrides):
    """A factory whose browser is `FakeAuthenticator`; the settings keep the session in the temporary folder."""
    s = settings(tmp_path, session_dir=tmp_path / ".session", **overrides)
    auth, reporter = FakeAuthenticator(site), Buffer()
    return CommandFactory(s, reporter, authenticator=auth, http_factory=site.http, ask=lambda: ("typed", "secret")), auth, reporter


def test_the_flag_is_in_the_command_line_and_off_by_default():
    parser = build_parser()
    assert parser.parse_args(["--login"]).login is True and parser.parse_args([]).login is False
    both = parser.parse_args(["--login", "--headed"])
    assert both.login and both.headed
    assert Settings.from_env(headed=True, environ={}).headless is False and Settings.from_env(environ={}).headless is True


def test_the_factory_builds_a_login_command_without_reading_the_catalog(tmp_path):
    factory, _, _ = login_with(tmp_path, FakeSite(), data_dir=tmp_path / "no-such-data-folder")
    assert isinstance(factory.create(build_parser().parse_args(["--login"])), LoginCommand)


def test_it_logs_in_checks_the_session_and_says_where_it_is_and_what_to_do_next(tmp_path):
    site = FakeSite()
    site.logged_in = False
    factory, auth, reporter = login_with(tmp_path, site)
    factory.create(build_parser().parse_args(["--login"])).execute()
    assert auth.calls == [("tester", "pw")] and site.logged_in
    assert reporter.lines == [f"Session saved in {tmp_path / '.session'}/. {FINAL}"]
    assert any(url.endswith("/projects/list?page=1") for url in site.requests)                   # (the check with what was saved)


def test_in_the_repository_the_session_is_shown_as_the_default_folder(tmp_path):
    site = FakeSite()
    reporter, auth = Buffer(), FakeAuthenticator(site)
    s = settings(tmp_path, session_dir=ROOT / ".session")
    factory = CommandFactory(s, reporter, authenticator=auth, http_factory=site.http)
    factory.create(build_parser().parse_args(["--login"])).execute()
    assert reporter.lines == [f"Session saved in .session/. {FINAL}"]


def test_it_logs_in_again_even_when_the_saved_session_still_works(tmp_path):
    site = FakeSite()
    factory, auth, _ = login_with(tmp_path, site)
    state = factory.settings.state_file
    state.parent.mkdir(parents=True), state.write_text("{}")
    factory.create(build_parser().parse_args(["--login"])).execute()
    assert len(auth.calls) == 1


def test_the_credentials_not_in_the_environment_are_asked_for(tmp_path):
    site = FakeSite()
    factory, auth, _ = login_with(tmp_path, site, login=None, password=None)
    factory.create(build_parser().parse_args(["--login"])).execute()
    assert auth.calls == [("typed", "secret")]


def test_a_login_the_intra_does_not_accept_is_an_error_and_no_success_message(tmp_path):
    site = FakeSite()
    site.logged_in = False

    class Useless(Authenticator):                  # logs in "successfully" but leaves nothing that works
        def login(self, login, password):
            pass

    reporter = Buffer()
    s = settings(tmp_path, session_dir=tmp_path / ".session")
    with pytest.raises(SystemExit, match="plain HTTP can't read the intra: not logged in"):
        main(["--login"], settings=s, reporter=reporter, factory=CommandFactory(s, reporter, authenticator=Useless(), http_factory=site.http))
    assert reporter.lines == []


def test_main_runs_it_and_a_missing_login_is_a_message_not_a_traceback(tmp_path):
    site = FakeSite()
    factory, auth, reporter = login_with(tmp_path, site)
    main(["--login"], settings=factory.settings, reporter=reporter, factory=factory)
    assert auth.calls and reporter.lines[-1].endswith(FINAL)
    bare = settings(tmp_path, login=None, password=None)
    with pytest.raises(SystemExit, match="Not logged in: set INTRA_LOGIN and INTRA_PASSWORD"):
        main(["--login"], settings=bare, reporter=Buffer(), factory=CommandFactory(bare, Buffer(), authenticator=FakeAuthenticator(site),
                                                                                    http_factory=site.http))
