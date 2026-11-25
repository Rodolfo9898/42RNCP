"""The app as a whole: the routes it offers (nothing else), the headers of every answer, and how a failure is told."""

from fastapi.testclient import TestClient

from tests.verdict.api.support import FakeScraper, new_session
from verdict.app.container import Container
from verdict.app.factory import create_app
from verdict.app.security import HEADERS
from verdict.app.settings import Settings
from verdict.gateways.scraper import NullScraper, ScraperGateway
from verdict.gateways.terminal import NullTerminal, TerminalGateway

ROUTES = {
    ("GET", "/api/health"), ("GET", "/api/environment"), ("GET", "/api/library"), ("POST", "/api/library/{track}/subjects"),
    ("GET", "/api/library/plan"), ("POST", "/api/library/downloads"), ("GET", "/api/library/downloads/current"),
    ("DELETE", "/api/library/downloads/current"), ("POST", "/api/library/reorganizations"),
    ("POST", "/api/sessions"), ("GET", "/api/sessions/{session_id}"), ("DELETE", "/api/sessions/{session_id}"),
    ("POST", "/api/sessions/{session_id}/subjects"), ("DELETE", "/api/sessions/{session_id}/subjects/{name}"),
    ("GET", "/api/sessions/{session_id}/subjects/{name}/pages/{page}.png"), ("GET", "/api/projects"),
    ("PUT", "/api/sessions/{session_id}/repo"), ("POST", "/api/sessions/{session_id}/runs"),
    ("PUT", "/api/sessions/{session_id}/claude-review"), ("POST", "/api/sessions/{session_id}/ai-review"),
    ("DELETE", "/api/sessions/{session_id}/ai-review"), ("GET", "/api/sessions/{session_id}/prompts/review"),
    ("GET", "/api/sessions/{session_id}/prompts/fix"), ("PUT", "/api/sessions/{session_id}/progress"),
    ("GET", "/api/sessions/{session_id}/verdict.md"),
}


def test_the_api_is_exactly_the_documented_one(client):
    """What the editor extension uses and nothing else: no tree, file, search, git, terminal or shell endpoint, and no pull one
    (every run pulls by itself)."""
    c, _ = client
    offered = {(method.upper(), path) for path, operations in c.app.openapi()["paths"].items() for method in operations}
    assert offered == ROUTES


def test_every_answer_carries_the_security_headers_even_a_failure(client):
    c, _ = client
    sid = new_session(c)
    answers = [c.get("/api/health"), c.get(f"/api/sessions/{sid}"), c.get("/api/sessions/nope"), c.post(f"/api/sessions/{sid}/runs"),
               c.get(f"/api/sessions/{sid}/verdict.md")]
    assert [a.status_code for a in answers] == [200, 200, 404, 400, 200]
    for answer in answers:
        assert all(answer.headers[name] == value for name, value in HEADERS.items())
        assert answer.headers["x-content-type-options"] == "nosniff" and answer.headers["referrer-policy"] == "no-referrer"
    csp = answers[0].headers["content-security-policy"]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp and "script-src" not in csp


def test_a_refusal_is_a_detail_and_a_status(client):
    c, _ = client
    sid = new_session(c)
    refused = c.post(f"/api/sessions/{sid}/runs")
    assert refused.status_code == 400 and refused.json() == {"detail": "clone a repository first"}
    unknown = c.get("/api/sessions/nope")
    assert unknown.status_code == 404 and unknown.json() == {"detail": "unknown session"}


def test_the_app_builds_its_own_container_from_the_settings(tmp_path):
    settings = Settings(workspace=tmp_path / "ws", projects=tmp_path / "projects", samples=tmp_path / "lib")
    c = TestClient(create_app(settings))
    container = c.app.state.container
    assert isinstance(container.terminal, NullTerminal) and container.settings is settings
    assert c.post("/api/sessions").status_code == 201 and (tmp_path / "projects").is_dir()


def test_the_terminal_gateway_is_used_only_when_it_is_configured(tmp_path):
    """The url alone is not enough: the token is what the terminal service asks for."""
    def container(url, token):
        return Container(Settings(workspace=tmp_path / "ws", projects=tmp_path / "p", samples=tmp_path / "s", terminal_url=url,
                                  terminal_token=token))

    assert isinstance(container("", "").terminal, NullTerminal) and isinstance(container("http://terminal:8002", "").terminal, NullTerminal)
    gateway = container("http://terminal:8002", "tok").terminal
    assert isinstance(gateway, TerminalGateway) and (gateway.url, gateway.token) == ("http://terminal:8002", "tok")


def test_settings_come_from_the_environment_once(tmp_path):
    settings = Settings.from_env({"WORKSPACE": str(tmp_path / "w"), "SAMPLES_DIR": str(tmp_path / "s"), "PROGRESS_FILE": str(tmp_path / "P.md"),
                                  "TERMINAL_URL": "http://terminal:8002/", "TERMINAL_TOKEN": "tok"})
    assert settings.workspace == tmp_path / "w" and settings.projects == tmp_path / "w" / "projects" and settings.samples == tmp_path / "s"
    assert settings.progress_file == tmp_path / "P.md" and settings.terminal_url == "http://terminal:8002" and settings.terminal_configured
    bare = Settings.from_env({"WORKSPACE": str(tmp_path / "w"), "PROJECTS_DIR": str(tmp_path / "elsewhere")})
    assert bare.progress_file is None and not bare.terminal_configured and bare.projects == tmp_path / "elsewhere"


def test_the_scraper_gateway_is_used_only_when_it_is_configured(tmp_path):
    """The url alone is not enough: the token is what the scraper service asks for."""
    def container(url, token, **kwargs):
        return Container(Settings(workspace=tmp_path / "ws", projects=tmp_path / "p", samples=tmp_path / "s", scraper_url=url,
                                  scraper_token=token), **kwargs)

    for url, token in (("", ""), ("http://scraper:8003", ""), ("", "tok")):
        assert type(container(url, token).scraper) is NullScraper              # (the gateway is a NullScraper too: the exact type tells)
    gateway = container("http://scraper:8003", "tok").scraper
    assert type(gateway) is ScraperGateway and (gateway.url, gateway.token) == ("http://scraper:8003", "tok")
    own = FakeScraper()
    assert container("http://scraper:8003", "tok", scraper=own).scraper is own and container("", "", scraper=own).downloads.scraper is own


def test_the_scraper_settings_come_from_the_environment(tmp_path):
    env = {"WORKSPACE": str(tmp_path / "w"), "SCRAPER_URL": "http://scraper:8003/", "SCRAPER_TOKEN": "tok"}
    settings = Settings.from_env(env)
    assert (settings.scraper_url, settings.scraper_token) == ("http://scraper:8003", "tok") and settings.scraper_configured
    for missing in ("SCRAPER_URL", "SCRAPER_TOKEN"):
        assert not Settings.from_env({k: v for k, v in env.items() if k != missing}).scraper_configured
    assert not Settings.from_env({"WORKSPACE": str(tmp_path / "w")}).scraper_configured
