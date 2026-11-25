"""src/scraper/server/auth.py and app.py: the token on every route but /health, the error shape, only the routes of the table."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scraper.server.app import create_app
from scraper.server.settings import ServiceSettings
from tests.scraper.support import HEADERS, TOKEN, make_world

GUARDED = [("GET", "/plan"), ("POST", "/downloads"), ("GET", "/downloads/current"), ("DELETE", "/downloads/current"),
           ("POST", "/reorganizations")]


@pytest.mark.parametrize("method,path", GUARDED)
def test_every_route_but_health_needs_the_token(world, method, path):
    client = world.client
    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers={"x-scraper-token": "wrong"}).status_code == 401
    assert client.request(method, path, headers={"x-scraper-token": TOKEN + "x"}).status_code == 401
    assert client.request(method, path, headers={"x-scraper-token": TOKEN[:-1]}).status_code == 401
    assert client.request(method, path, headers={"x-scraper-token": "tökén".encode("latin-1")}).status_code == 401      # (not ASCII: refused)
    assert client.request(method, path, headers=HEADERS).status_code != 401


@pytest.mark.parametrize("method,path", GUARDED)
def test_without_a_configured_token_everything_is_refused(tmp_path, method, path):
    world = make_world(tmp_path)
    client = TestClient(create_app(ServiceSettings("", world.settings), http_factory=world.site.http))
    assert client.request(method, path, headers={"x-scraper-token": ""}).status_code == 401
    assert client.request(method, path).status_code == 401
    assert client.get("/health").status_code == 200


def test_a_refusal_says_so_and_does_nothing(world):
    answer = world.client.post("/downloads")
    assert answer.status_code == 401 and answer.json() == {"detail": "bad token"}
    assert world.starter.started == 0 and world.site.requests == []


def test_health_is_open(world):
    for headers in ({}, HEADERS, {"x-scraper-token": "wrong"}):
        answer = world.client.get("/health", headers=headers)
        assert answer.status_code == 200 and answer.json() == {"status": "ok"}


def test_only_the_routes_of_the_table_exist_and_the_generated_docs_are_off(world):
    for method, path in (("GET", "/docs"), ("GET", "/redoc"), ("GET", "/openapi.json"), ("GET", "/downloads"), ("GET", "/reorganizations"),
                         ("DELETE", "/plan"), ("PUT", "/downloads/current"), ("GET", "/downloads/other")):
        assert world.client.request(method, path, headers=HEADERS).status_code in (404, 405), (method, path)
    assert world.client.get("/docs").status_code == 404


def test_a_body_that_does_not_fit_is_a_422_with_a_plain_detail(world):
    for body in ({"tracks": "common-core"}, {"projects": [""]}, {"artifacts": "perhaps"}, {"tracks": ["x"] * 11}, {"projects": ["p" * 121]}):
        answer = world.post("/downloads", body)
        assert answer.status_code == 422 and isinstance(answer.json()["detail"], str), body
    answer = world.client.post("/downloads", headers=HEADERS, content=b"{not json", params={})
    assert answer.status_code == 422 and isinstance(answer.json()["detail"], str)
    assert world.starter.started == 0


def test_a_missing_body_means_the_defaults(world):
    assert world.client.post("/reorganizations", headers=HEADERS).json()["dry_run"] is True       # (looking, not moving)
    assert world.client.post("/downloads", headers=HEADERS).status_code == 202
