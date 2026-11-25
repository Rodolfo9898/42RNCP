"""src/scraper/server/settings.py and src/scraper_server.py: the environment the service reads, and the main that wires and starts."""
from __future__ import annotations

import runpy
import subprocess
import sys

import pytest
from fastapi import FastAPI

from scraper.core.config import ROOT
from scraper.core.exceptions import ScraperError
from scraper.server.settings import ServiceSettings
from tests.paths import SRC

ENVIRONMENT = {"SCRAPER_TOKEN": "t0ken", "SAMPLES_DIR": "/data/samples", "ARTIFACTS_DIR": "/data/artifacts", "SESSION_DIR": "/session",
               "SCRAPE_DELAY": "0.25", "SUBJECT_LANG": "FR"}


def test_the_service_reads_its_settings_from_the_environment():
    settings = ServiceSettings.from_environment(ENVIRONMENT)
    assert settings.token == "t0ken"
    s = settings.scraper
    assert (str(s.samples_dir), str(s.artifacts_dir), str(s.session_dir)) == ("/data/samples", "/data/artifacts", "/session")
    assert (s.delay, s.lang) == (0.25, "fr")
    assert (str(s.state_file), str(s.user_agent_file)) == ("/session/state.json", "/session/user_agent.txt")


def test_the_defaults_are_the_ones_of_the_command_line():
    s = ServiceSettings.from_environment({"SCRAPER_TOKEN": "t"}).scraper
    assert (s.samples_dir, s.artifacts_dir, s.session_dir) == (ROOT / "samples", ROOT / "artifacts", ROOT / ".session")
    assert (s.delay, s.lang, s.with_artifacts, s.with_children) == (1.5, "en", True, True)


@pytest.mark.parametrize("environ", [{}, {"SCRAPER_TOKEN": ""}, {"SAMPLES_DIR": "/data/samples"}])
def test_it_refuses_to_start_without_the_token(environ):
    with pytest.raises(ScraperError, match="SCRAPER_TOKEN"):
        ServiceSettings.from_environment(environ)


def test_it_never_holds_the_intra_login():
    settings = ServiceSettings.from_environment({"SCRAPER_TOKEN": "t", "INTRA_LOGIN": "me", "INTRA_PASSWORD": "secret"})
    assert settings.scraper.login is None and settings.scraper.password is None
    assert "secret" not in repr(settings)


def test_the_main_builds_the_app_from_the_environment(monkeypatch):
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    app = runpy.run_module("scraper_server")["app"]
    assert isinstance(app, FastAPI) and app.docs_url is None and app.openapi_url is None


def test_the_main_does_not_start_without_the_token(monkeypatch):
    monkeypatch.delenv("SCRAPER_TOKEN", raising=False)
    with pytest.raises(ScraperError, match="SCRAPER_TOKEN"):
        runpy.run_module("scraper_server")


def test_the_service_imports_neither_playwright_nor_the_other_features(tmp_path):
    """The image holds fastapi, uvicorn and httpx and nothing else: no browser, and none of what the other containers are for."""
    code = (f"import sys; sys.path.insert(0, {str(SRC)!r})\n"
            "for name in ('playwright', 'playwright.sync_api', 'pymupdf', 'anthropic', 'multipart', 'verdict', 'terminal', 'sandbox', 'shared'):\n"
            "    sys.modules[name] = None             # importing any of them now fails\n"
            "import scraper.server.app, scraper.jobs.runner, scraper.cli.login\n")
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, cwd=tmp_path)
    assert run.returncode == 0, run.stderr
