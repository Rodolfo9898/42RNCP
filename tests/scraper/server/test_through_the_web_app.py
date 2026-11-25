"""The two halves of the feature meet here: the web app's gateway talks to the scraper service (in this process, no socket) over the
contract, and the library the web app reads is the one the download filled."""
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from tests.scraper.support import TOKEN, make_world
from verdict.app.container import Container
from verdict.app.factory import create_app
from verdict.app.settings import Settings
from verdict.gateways.scraper import ScraperGateway


def web_over(world, *, token: str = TOKEN) -> TestClient:
    """The real web app whose gateway reaches `world`'s service: every request is handed to the service's app as it is."""
    def forward(request: httpx.Request) -> httpx.Response:
        target = request.url.raw_path.decode()
        reply = world.client.request(request.method, target, headers=dict(request.headers), content=request.content)
        return httpx.Response(reply.status_code, headers={"content-type": reply.headers["content-type"]}, content=reply.content)

    settings = Settings(workspace=world.tmp / "ws", projects=world.tmp / "projects", samples=world.tmp / "samples")
    gateway = ScraperGateway("http://scraper:8003", token, transport=httpx.MockTransport(forward))
    return TestClient(create_app(container=Container(settings, sandbox=None, scraper=gateway)))


def test_what_is_missing_a_download_and_the_library_it_filled(tmp_path):
    world = make_world(tmp_path)
    web = web_over(world)
    plan = web.get("/api/library/plan", params={"track": "common-core"}).json()
    assert plan["ready"] is True and plan["session"]["valid"] is True and [t["track"] for t in plan["tracks"]] == ["common-core"]
    common = plan["tracks"][0]
    assert common["label"] == "Common Core" and common["with_pdf"] == 0 and common["total"] == len(common["missing"]) == 3
    assert {m["path"] for m in common["missing"]} == {"common-core/libft.pdf", "common-core/cpp-modules/cpp00.pdf", "common-core/cpp-modules/cpp01.pdf"}

    started = web.post("/api/library/downloads", json={"tracks": ["common-core"], "artifacts": False})
    assert started.status_code == 202 and started.json()["state"] == "running"
    second = web.post("/api/library/downloads", json={})                                  # (one at a time: the service says so while it runs)
    assert second.status_code == 409 and second.json()["detail"]
    world.starter.run()
    done = web.get("/api/library/downloads/current", params={"since": 0}).json()
    assert done["state"] == "done" and done["summary"]["downloaded_subjects"] == 3 and done["next"] == len(done["lines"]) > 0
    assert web.get("/api/library/downloads/current", params={"since": done["next"]}).json()["lines"] == []

    listing = web.get("/api/library").json()
    assert {"common-core/libft.pdf", "common-core/cpp-modules/cpp00.pdf"} <= {item["path"] for item in listing["items"]}      # the app reads the series folders
    assert web.get("/api/library/plan", params={"track": "common-core"}).json()["tracks"][0]["missing"] == []


def test_a_reorganization_through_the_web_app_lists_then_moves(tmp_path):
    world = make_world(tmp_path)
    world.pdf("common-core/cpp00.pdf")
    web = web_over(world)
    assert web.get("/api/library/plan", params={"track": "common-core"}).json()["misplaced"] == 1
    listed = web.post("/api/library/reorganizations", json={"dry_run": True}).json()
    assert listed == {"dry_run": True, "done": 0, "moves": [{"from": "samples/common-core/cpp00.pdf", "to": "samples/common-core/cpp-modules/cpp00.pdf"}]}
    assert (tmp_path / "samples/common-core/cpp00.pdf").exists()
    moved = web.post("/api/library/reorganizations", json={"dry_run": False}).json()
    assert moved["done"] == 1 and (tmp_path / "samples/common-core/cpp-modules/cpp00.pdf").is_file()
    assert web.delete("/api/library/downloads/current").json() == {"state": "idle"}


def test_without_a_saved_session_the_editor_is_told_to_log_in_on_the_computer(tmp_path):
    web = web_over(make_world(tmp_path, session=False))
    plan = web.get("/api/library/plan").json()
    assert plan["ready"] is False and "make samples-login" in plan["session"]["reason"]
    refused = web.post("/api/library/downloads", json={})
    assert refused.status_code == 400 and "make samples-login" in refused.json()["detail"]


def test_a_service_that_refuses_the_token_is_an_unavailable_downloader_and_never_echoes_the_token(tmp_path):
    answer = web_over(make_world(tmp_path), token="not-the-token").get("/api/library/plan")
    assert answer.status_code == 503 and "not-the-token" not in answer.text and TOKEN not in answer.text
