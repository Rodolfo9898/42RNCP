"""Getting subjects from the 42 intra through the subject downloader: the five routes, what they refuse, and how the downloader's own
refusals are told. The downloader is the harness's `FakeScraper`; the HTTP to the real one is tested in tests/verdict/gateways."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SUBJECT_PAGES, make_pdf
from verdict.app.factory import create_app
from verdict.app.settings import Settings
from verdict.core.errors import Conflict, Failed, Unavailable, VerdictError

NOT_CONFIGURED = {"detail": "the subject downloader is not configured"}
EVERYTHING = {"tracks": None, "projects": None, "artifacts": True, "children": True, "force": False}

ROUTES = [("GET", "/api/library/plan", {}), ("POST", "/api/library/downloads", {"json": {}}), ("GET", "/api/library/downloads/current", {}),
          ("DELETE", "/api/library/downloads/current", {}), ("POST", "/api/library/reorganizations", {"json": {}})]
CALLS = ["plan", "start_download", "current_download", "cancel_download", "reorganize"]


def test_the_plan_is_the_downloaders_with_a_flag_that_says_a_download_can_start(client, scraper):
    c, _ = client
    scraper.answers["plan"] = {"session": {"valid": True, "reason": ""}, "misplaced": 2, "unknown": ["nope"], "tracks": [
        {"track": "rncp", "label": "RNCP", "total": 2, "with_pdf": 1, "missing": [{"name": "h42n42", "path": "rncp/h42n42.pdf", "slug": "h42n42"}]}]}
    answer = c.get("/api/library/plan")
    assert answer.status_code == 200
    assert answer.json() == {**scraper.answers["plan"], "ready": True}
    assert "ready" not in scraper.answers["plan"]                              # (the downloader's answer is not changed, a copy is)
    assert answer.json()["tracks"][0]["missing"][0]["path"] == "rncp/h42n42.pdf"


def test_the_plan_is_not_ready_when_the_session_is_not_usable_and_says_why(client, scraper):
    c, _ = client
    reason = "no saved session: run `make samples-login` on your computer"
    scraper.answers["plan"]["session"] = {"valid": False, "reason": reason}
    answer = c.get("/api/library/plan").json()
    assert answer["ready"] is False and answer["session"] == {"valid": False, "reason": reason}


@pytest.mark.parametrize("session", [None, "valid", {}, {"valid": "yes"}, {"valid": 1}, [True]])
def test_a_plan_that_does_not_say_clearly_that_the_session_is_valid_is_not_ready(client, scraper, session):
    c, _ = client
    scraper.answers["plan"]["session"] = session
    assert c.get("/api/library/plan").json()["ready"] is False
    del scraper.answers["plan"]["session"]
    assert c.get("/api/library/plan").json()["ready"] is False


def test_the_plan_asks_for_every_track_with_the_children_by_default_or_for_the_ones_named(client, scraper):
    c, _ = client
    c.get("/api/library/plan")
    c.get("/api/library/plan?track=rncp&track=common-core&children=false")
    assert scraper.of("plan") == [("plan", [], True), ("plan", ["rncp", "common-core"], False)]


@pytest.mark.parametrize("query", ["track=elsewhere", "track=rncp&track=", "track=Common-Core", "children=maybe",
                                   "track=rncp&track=common-core&track=post-common-core&track=rncp"])
def test_a_plan_that_asks_for_something_unknown_is_refused_before_the_downloader_is_asked(client, scraper, query):
    c, _ = client
    assert c.get(f"/api/library/plan?{query}").status_code == 422
    assert scraper.calls == []


def test_a_download_starts_for_everything_the_library_lacks_when_nothing_is_named(client, scraper):
    c, _ = client
    answer = c.post("/api/library/downloads", json={})
    assert answer.status_code == 202 and answer.json() == {"id": "d1", "state": "running"}
    assert scraper.of("start_download") == [("start_download", EVERYTHING)]
    assert c.post("/api/library/downloads", json={"tracks": None, "projects": None}).status_code == 202
    assert scraper.of("start_download")[-1] == ("start_download", EVERYTHING)


def test_a_download_passes_what_was_chosen_on_as_it_is(client, scraper):
    c, _ = client
    body = {"tracks": ["rncp", "post-common-core"], "projects": ["libft", "42cursus-libft", "Django - 0", "1314", "so_long.pdf"],
            "artifacts": False, "children": False, "force": True}
    assert c.post("/api/library/downloads", json=body).status_code == 202
    assert scraper.of("start_download") == [("start_download", body)]


@pytest.mark.parametrize("body", [
    {"tracks": ["elsewhere"]}, {"tracks": ["rncp", "Common Core"]}, {"tracks": "rncp"}, {"tracks": []},
    {"tracks": ["rncp", "common-core", "post-common-core", "rncp"]},
    {"projects": []}, {"projects": "libft"}, {"projects": [""]}, {"projects": ["   "]}, {"projects": [7]}, {"projects": [None]},
    {"projects": ["lib\nft"]}, {"projects": ["lib\x00ft"]}, {"projects": ["lib\x1b[2Jft"]}, {"projects": ["lib\x7fft"]}, {"projects": ["lib\tft"]},
    {"projects": ["lib ft"]}, {"projects": ["a" * 101]}, {"projects": ["libft"] * 201},
    {"artifacts": "maybe"}, {"children": []}, {"force": {}}, {"project": ["libft"]}, {"tracks": ["rncp"], "extra": 1},
])
def test_a_download_that_names_something_it_cannot_be_is_refused_and_nothing_starts(client, scraper, body):
    c, _ = client
    answer = c.post("/api/library/downloads", json=body)
    assert answer.status_code == 422 and isinstance(answer.json()["detail"], list)
    assert scraper.calls == []


@pytest.mark.parametrize("content", [None, "", "[]", "null", "libft", "{not json"])
def test_a_download_needs_a_json_object_as_its_body(client, scraper, content):
    c, _ = client
    answer = c.post("/api/library/downloads", content=content, headers={"content-type": "application/json"})
    assert answer.status_code == 422 and scraper.calls == []


def test_the_longest_name_and_the_longest_list_that_are_allowed_go_through(client, scraper):
    c, _ = client
    body = {"projects": [f"{n:03}" + "a" * 97 for n in range(200)]}
    assert c.post("/api/library/downloads", json=body).status_code == 202
    assert scraper.of("start_download")[0][1]["projects"] == body["projects"]
    assert c.post("/api/library/downloads", json={"projects": ["é ü - 0.pdf"], "tracks": ["rncp", "common-core", "post-common-core"]}).status_code == 202


def test_the_state_of_the_download_and_its_new_lines_are_asked_from_a_line_on(client, scraper):
    c, _ = client
    running = {"state": "running", "id": "d1", "lines": ["Downloading libft"], "next": 4, "summary": None}
    scraper.answers["current_download"] = running
    assert c.get("/api/library/downloads/current").json() == running
    assert c.get("/api/library/downloads/current?since=3").json() == running
    assert scraper.of("current_download") == [("current_download", 0), ("current_download", 3)]


@pytest.mark.parametrize("since", ["-1", "x", "1.5", "", "0x10"])
def test_a_line_to_start_from_that_is_not_a_number_of_zero_or_more_is_refused(client, scraper, since):
    c, _ = client
    assert c.get(f"/api/library/downloads/current?since={since}").status_code == 422
    assert scraper.calls == []


def test_a_download_is_stopped_and_the_state_is_told(client, scraper):
    c, _ = client
    scraper.answers["cancel_download"] = {"state": "running"}
    answer = c.delete("/api/library/downloads/current")
    assert answer.status_code == 200 and answer.json() == {"state": "running"}
    assert scraper.of("cancel_download") == [("cancel_download",)]


def test_a_reorganization_is_only_a_list_of_moves_unless_it_is_asked_to_be_applied(client, scraper):
    c, _ = client
    moves = [{"from": "samples/common-core/cpp00.pdf", "to": "samples/common-core/cpp-modules/cpp00.pdf"}]
    scraper.answers["reorganize"] = {"dry_run": True, "done": 0, "moves": moves}
    assert c.post("/api/library/reorganizations").json() == {"dry_run": True, "done": 0, "moves": moves}      # (no body at all)
    c.post("/api/library/reorganizations", json={})
    c.post("/api/library/reorganizations", json={"dry_run": True})
    c.post("/api/library/reorganizations", json={"dry_run": False})
    assert scraper.of("reorganize") == [("reorganize", True)] * 3 + [("reorganize", False)]


@pytest.mark.parametrize("body", [{"dry_run": "maybe"}, {"dry_run": None}, {"dry_run": []}, {"dry": False}, {"dry_run": False, "extra": 1}])
def test_a_reorganization_that_is_not_clearly_asked_for_is_refused(client, scraper, body):
    c, _ = client
    assert c.post("/api/library/reorganizations", json=body).status_code == 422
    assert scraper.calls == []


@pytest.mark.parametrize("error, status", [
    (VerdictError("the saved session is not usable: run `make samples-login` on your computer (it expired)"), 400),
    (Conflict("a download is already running"), 409),
    (Unavailable("could not reach the subject downloader (is the scraper service running?)"), 503),
    (Failed("the subject downloader answered HTTP 500"), 500),
])
@pytest.mark.parametrize("method, path, kwargs", ROUTES)
def test_what_the_downloader_refuses_is_told_with_its_status_and_its_words_by_every_route(client, scraper, method, path, kwargs, error, status):
    c, _ = client
    scraper.error = error
    answer = c.request(method, path, **kwargs)
    assert answer.status_code == status and answer.json() == {"detail": error.message}


@pytest.fixture
def unconfigured(tmp_path):
    """The real app built from settings that name no downloader: its Null Object is what answers."""
    settings = Settings(workspace=tmp_path / "ws", projects=tmp_path / "projects", samples=tmp_path / "lib")
    return TestClient(create_app(settings))


@pytest.mark.parametrize("method, path, kwargs", ROUTES)
def test_without_a_downloader_every_route_says_it_is_not_configured(unconfigured, method, path, kwargs):
    answer = unconfigured.request(method, path, **kwargs)
    assert answer.status_code == 503 and answer.json() == NOT_CONFIGURED


def test_without_a_downloader_the_rest_of_the_library_works_and_a_bad_request_is_still_refused_first(unconfigured):
    assert unconfigured.get("/api/library").status_code == 200
    assert unconfigured.post("/api/library/downloads", json={"tracks": ["elsewhere"]}).status_code == 422
    assert unconfigured.get("/api/library/downloads/current?since=-1").status_code == 422


def test_the_routes_do_not_take_the_place_of_the_upload_of_a_track_nor_the_other_way_round(client, scraper):
    c, _ = client
    pdf = ("files", ("lib.pdf", make_pdf(SUBJECT_PAGES), "application/pdf"))
    assert c.post("/api/library/common-core/subjects", files=[pdf]).status_code == 201
    for word in ("plan", "downloads", "reorganizations"):                       # (a track that is called like a route is still no track)
        refused = c.post(f"/api/library/{word}/subjects", files=[pdf])
        assert refused.status_code == 400 and refused.json()["detail"].startswith("choose where the subject belongs")
    assert scraper.calls == []
    assert c.post("/api/library/downloads", json={}).status_code == 202
    assert c.get("/api/library/downloads/current").status_code == 200 and c.delete("/api/library/downloads/current").status_code == 200
    assert c.get("/api/library/plan").status_code == 200 and c.post("/api/library/reorganizations", json={}).status_code == 200
    assert [call[0] for call in scraper.calls] == ["start_download", "current_download", "cancel_download", "plan", "reorganize"]
    assert [i["path"] for i in c.get("/api/library").json()["items"]] == ["common-core/lib.pdf", "common-core/push_swap.pdf"]


@pytest.mark.parametrize("method, path", [("PUT", "/api/library/downloads"), ("GET", "/api/library/downloads"), ("POST", "/api/library/plan"),
                                          ("POST", "/api/library/downloads/current"), ("GET", "/api/library/reorganizations"),
                                          ("DELETE", "/api/library/plan")])
def test_a_route_answers_only_the_methods_it_has(client, scraper, method, path):
    c, _ = client
    assert c.request(method, path).status_code == 405 and scraper.calls == []


def test_the_listing_of_the_library_reads_the_folders_again_after_a_download_and_a_reorganization(client, scraper):
    c, harness = client
    first = [i["path"] for i in c.get("/api/library").json()["items"]]
    assert first == ["common-core/push_swap.pdf"]
    assert c.post("/api/library/downloads", json={"tracks": ["rncp"]}).status_code == 202
    (harness.settings.samples / "rncp").mkdir()                                  # what the downloader saves
    (harness.settings.samples / "rncp" / "h42n42.pdf").write_bytes(make_pdf(SUBJECT_PAGES))
    assert [i["path"] for i in c.get("/api/library").json()["items"]] == ["common-core/push_swap.pdf", "rncp/h42n42.pdf"]
    series = harness.settings.samples / "rncp" / "piscine"
    series.mkdir()
    (harness.settings.samples / "rncp" / "h42n42.pdf").rename(series / "h42n42.pdf")      # what a reorganization does
    assert c.post("/api/library/reorganizations", json={"dry_run": False}).status_code == 200
    assert [i["path"] for i in c.get("/api/library").json()["items"]] == ["common-core/push_swap.pdf", "rncp/piscine/h42n42.pdf"]
