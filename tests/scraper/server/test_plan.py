"""GET /plan: the data of the PlanReport (offline) and the status of the saved session."""
from __future__ import annotations

import httpx
import pytest

from tests.scraper.support import make_world


def by_track(answer: dict) -> dict[str, dict]:
    return {t["track"]: t for t in answer["tracks"]}


def test_the_plan_is_structured_per_track_with_what_is_missing(world):
    answer = world.get("/plan").json()
    assert set(answer) == {"session", "tracks", "unknown", "misplaced"}
    tracks = by_track(answer)
    assert [t["track"] for t in answer["tracks"]] == ["common-core", "post-common-core", "rncp"]
    assert {k: tracks["common-core"][k] for k in ("label", "total", "with_pdf")} == {"label": "Common Core", "total": 3, "with_pdf": 0}
    assert tracks["post-common-core"]["label"] == "Post Common Core" and tracks["rncp"]["label"] == "RNCP"
    assert set(tracks["common-core"]) == {"track", "label", "total", "with_pdf", "missing"}
    assert tracks["common-core"]["missing"] == [
        {"name": "cpp00", "path": "common-core/cpp-modules/cpp00.pdf", "slug": "cpp-module-00"},
        {"name": "cpp01", "path": "common-core/cpp-modules/cpp01.pdf", "slug": "cpp-module-01"},
        {"name": "libft", "path": "common-core/libft.pdf", "slug": "42cursus-libft"}]
    assert [m["path"] for m in tracks["rncp"]["missing"]] == ["rncp/h42n42.pdf", "rncp/piscine-swift/piscine-swift.pdf",
                                                              "rncp/piscine-swift/swift-0-intro.pdf"]          # (a piscine has a folder of its own)
    assert [m["path"] for m in tracks["post-common-core"]["missing"]] == ["post-common-core/darkly.pdf"]
    assert answer["misplaced"] == 0


def test_what_is_on_disk_counts_wherever_it_is_and_whatever_its_spelling(world):
    world.pdf("common-core/Libft.pdf")
    world.pdf("common-core/cpp-modules/cpp00.pdf")
    tracks = by_track(world.get("/plan").json())
    assert tracks["common-core"]["with_pdf"] == 2 and [m["name"] for m in tracks["common-core"]["missing"]] == ["cpp01"]
    assert tracks["rncp"]["with_pdf"] == 0


def test_names_the_catalog_does_not_know_are_listed(world):
    assert world.get("/plan").json()["unknown"] == ["ft_lex"]
    assert world.get("/plan", track="common-core").json()["unknown"] == []


def test_pdfs_not_in_the_folder_of_their_series_are_counted_as_misplaced(world):
    world.pdf("common-core/cpp00.pdf")
    world.pdf("common-core/cpp01.pdf")
    world.pdf("common-core/libft.pdf")
    answer = world.get("/plan").json()
    assert answer["misplaced"] == 2
    assert by_track(answer)["common-core"]["with_pdf"] == 3 and by_track(answer)["common-core"]["missing"] == []


def test_the_tracks_can_be_narrowed_and_a_track_that_does_not_exist_is_refused(world):
    assert [t["track"] for t in world.get("/plan", track="rncp").json()["tracks"]] == ["rncp"]
    assert [t["track"] for t in world.get("/plan", track=["rncp", "common-core"]).json()["tracks"]] == ["common-core", "rncp"]
    answer = world.get("/plan", track="common_core")
    assert answer.status_code == 400 and "unknown track 'common_core'" in answer.json()["detail"]


def test_the_children_of_a_piscine_can_be_left_out(world):
    assert by_track(world.get("/plan").json())["rncp"]["total"] == 3
    without = by_track(world.get("/plan", children="false").json())["rncp"]
    assert without["total"] == 2 and [m["name"] for m in without["missing"]] == ["h42n42", "piscine-swift"]
    assert world.get("/plan", children="false").json()["session"]["valid"] is True


def test_the_plan_reads_the_folders_and_asks_the_intra_one_question_only(world):
    world.get("/plan")
    assert [url.rsplit("/", 1)[-1].split("?")[0] for url in world.site.requests] == ["list"]
    assert not (world.tmp / "artifacts").exists()


# ----------------------------------------------------------------------------------------- the session


def test_a_session_that_works_is_valid(world):
    assert world.get("/plan").json()["session"] == {"valid": True, "reason": ""}


def test_without_a_saved_session_it_says_where_to_log_in(tmp_path):
    world = make_world(tmp_path, session=False)
    answer = world.get("/plan")
    assert answer.status_code == 200
    assert answer.json()["session"] == {"valid": False, "reason": "no saved session: run `make samples-login` on your computer"}
    assert world.site.requests == []                                    # (nothing to try the intra with)
    assert len(answer.json()["tracks"]) == 3                            # and the rest of the plan is there all the same


def test_a_session_the_intra_turned_down_gives_the_reason_of_the_access_check(world):
    world.site.logged_in = False
    assert world.get("/plan").json()["session"] == {"valid": False, "reason": "not logged in (redirected to the sign-in page)"}
    world.site.logged_in, world.site.cloudflare = True, True
    session = world.get("/plan").json()["session"]
    assert session["valid"] is False and "Cloudflare" in session["reason"]


def test_a_network_failure_is_a_reason_and_never_an_error(world):
    def down(request):
        raise httpx.ConnectError("name resolution failed")

    world.site.handler = down
    answer = world.get("/plan")
    assert answer.status_code == 200
    assert answer.json()["session"]["valid"] is False and "could not reach the 42 intra" in answer.json()["session"]["reason"]
    assert len(answer.json()["tracks"]) == 3


@pytest.mark.parametrize("content", ["{not json", '{"cookies": [{"value": "no name"}]}'])
def test_a_saved_session_that_cannot_be_read_is_a_reason_too(tmp_path, content):
    world = make_world(tmp_path, own_http=True)                          # (the service builds its client from the saved file)
    world.settings.state_file.write_text(content)
    answer = world.get("/plan")
    assert answer.status_code == 200
    assert answer.json()["session"]["valid"] is False and "could not be read" in answer.json()["session"]["reason"]
