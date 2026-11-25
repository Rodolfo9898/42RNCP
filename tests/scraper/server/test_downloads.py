"""POST /downloads and GET /downloads/current: a download against the in-memory intra, from the request to the summary."""
from __future__ import annotations

import pytest

from tests.scraper.support import make_world
from tests.scraper.test_scraper import PDF, page

IDLE = {"state": "idle", "id": "", "lines": [], "next": 0, "summary": None}
COMMON_CORE = {"tracks": ["common-core"]}


def current(world, since: int = 0) -> dict:
    return world.get("/downloads/current", since=str(since)).json()


def test_before_the_first_download_the_state_is_idle(world):
    assert current(world) == IDLE
    assert world.delete("/downloads/current").json() == {"state": "idle"}


def test_a_download_starts_at_once_and_ends_with_the_files_and_a_summary(world):
    answer = world.post("/downloads", COMMON_CORE)
    assert answer.status_code == 202 and answer.json() == {"id": "job-1", "state": "running"}
    before = current(world)
    assert (before["state"], before["id"], before["lines"], before["next"], before["summary"]) == ("running", "job-1", [], 0, None)
    world.starter.run()
    after = current(world)
    assert after["state"] == "done" and after["id"] == "job-1"
    assert after["summary"] == {"downloaded_subjects": 3, "downloaded_artifacts": 3, "existing": 0, "failed": [], "no_files": []}
    assert after["lines"][0] == "3 project(s) selected, 3 to visit." and any(line.startswith("Done: 3 subject(s) and 3 artifact(s)") for line in after["lines"])
    assert (world.tmp / "samples/common-core/libft.pdf").read_bytes() == PDF
    assert (world.tmp / "samples/common-core/cpp-modules/cpp00.pdf").is_file() and (world.tmp / "artifacts/cpp-modules/cpp01/tests.tgz").is_file()
    assert not (world.tmp / "samples/rncp").exists()                            # (only the track that was asked for)


def test_the_lines_come_in_pieces_when_asked_from_where_you_stopped(world):
    seen = []
    world.site.on_page["cpp-module-00"] = lambda: seen.append(current(world))
    world.site.on_page["cpp-module-01"] = lambda: seen.append(current(world, seen[-1]["next"]))
    world.post("/downloads", COMMON_CORE)
    world.starter.run()
    first, second = seen
    assert first["state"] == second["state"] == "running" and first["summary"] is None
    assert first["lines"][0] == "3 project(s) selected, 3 to visit." and first["lines"][-1] == "[1/3] common-core/cpp00  (cpp-module-00)"
    assert second["lines"] and any("cpp00.pdf" in line for line in second["lines"])
    full = current(world)
    assert full["lines"][:first["next"]] == first["lines"] and full["lines"][first["next"]:second["next"]] == second["lines"]
    assert first["next"] == len(first["lines"]) and second["next"] == first["next"] + len(second["lines"]) and full["next"] == len(full["lines"])
    rest = current(world, second["next"])
    assert rest["lines"] == full["lines"][second["next"]:] and rest["next"] == full["next"]
    assert current(world, full["next"])["lines"] == [] and current(world, full["next"] + 50) == {**full, "lines": []}


def test_the_numbers_of_the_summary_come_from_what_the_run_did(world):
    world.pdf("common-core/libft.pdf")                                          # there already: only its artifacts are fetched
    world.site.add_project("cpp-module-00", "cpp00", artifacts=("tests.tgz",), broken_subject=True)
    world.site.projects["cpp-module-01"] = page("<h1>Intra Projects cpp01</h1>")           # a page with no files on it
    world.post("/downloads", COMMON_CORE)
    world.starter.run()
    done = current(world)
    assert done["state"] == "done"
    assert done["summary"] == {"downloaded_subjects": 0, "downloaded_artifacts": 2, "existing": 1,
                               "failed": ["samples/common-core/cpp-modules/cpp00.pdf"], "no_files": ["cpp01 (cpp-module-01)"]}
    assert any("1 failure(s)" in line for line in done["lines"]) and any("No files found for 1 project(s)" in line for line in done["lines"])


def test_a_run_with_nothing_to_do_is_done_with_a_summary_of_zeros(world):
    world.post("/downloads", {"tracks": ["rncp"], "projects": ["libft"]})                 # libft is not in that track
    world.starter.run()
    done = current(world)
    assert done["state"] == "done" and done["lines"][-1].startswith("Nothing to do")
    assert done["summary"] == {"downloaded_subjects": 0, "downloaded_artifacts": 0, "existing": 0, "failed": [], "no_files": []}


def test_the_options_of_the_request_reach_the_download(world):
    world.post("/downloads", {"projects": ["libft"], "artifacts": False})
    world.starter.run()
    assert (world.tmp / "samples/common-core/libft.pdf").is_file() and not (world.tmp / "artifacts/libft").exists()
    assert current(world)["summary"]["downloaded_artifacts"] == 0
    world.pdf("common-core/libft.pdf", b"old")
    world.post("/downloads", {"projects": ["libft"], "artifacts": False})
    world.starter.run()
    assert (world.tmp / "samples/common-core/libft.pdf").read_bytes() == b"old" and "Nothing to do" in current(world)["lines"][-1]
    world.post("/downloads", {"projects": ["libft"], "artifacts": False, "force": True})
    world.starter.run()
    assert (world.tmp / "samples/common-core/libft.pdf").read_bytes() == PDF


def test_the_children_of_a_piscine_come_unless_they_are_left_out(world):
    world.post("/downloads", {"tracks": ["rncp"], "children": False, "artifacts": False})
    world.starter.run()
    assert sorted(p.name for p in (world.tmp / "samples/rncp").rglob("*.pdf")) == ["h42n42.pdf", "piscine-swift.pdf"]
    world.post("/downloads", {"tracks": ["rncp"], "artifacts": False})
    world.starter.run()
    assert (world.tmp / "samples/rncp/piscine-swift/swift-0-intro.pdf").is_file()


def test_a_finished_download_stays_readable_until_the_next_one_starts(world):
    world.post("/downloads", {"projects": ["libft"]})
    world.starter.run()
    done = current(world)
    assert done["state"] == "done" and current(world) == done
    assert world.post("/downloads", {"projects": ["darkly"]}).json() == {"id": "job-2", "state": "running"}
    assert current(world)["id"] == "job-2" and current(world)["lines"] == []


def test_only_one_download_runs_at_a_time(world):
    assert world.post("/downloads", COMMON_CORE).status_code == 202
    asked_before = len(world.site.requests)
    answer = world.post("/downloads", {"projects": ["darkly"]})
    assert answer.status_code == 409 and "already running" in answer.json()["detail"]
    assert len(world.site.requests) == asked_before                         # (turned away without asking the intra anything)
    assert world.starter.started == 1 and current(world)["id"] == "job-1"
    world.starter.run()
    assert world.post("/downloads", {"projects": ["darkly"]}).status_code == 202


def test_the_download_in_the_background_thread_is_the_same_as_the_one_run_by_hand(eager):
    assert eager.post("/downloads", {"projects": ["libft"]}).status_code == 202
    assert current(eager)["state"] == "done" and (eager.tmp / "samples/common-core/libft.pdf").is_file()


# ------------------------------------------------------------------------------ refused before anything starts


@pytest.mark.parametrize("project,detail", [("nope", "catalog does not know"), ("exam-rank-02", "in no track")])
def test_an_unknown_project_is_a_400_and_nothing_starts(world, project, detail):
    answer = world.post("/downloads", {"projects": ["libft", project]})
    assert answer.status_code == 400 and detail in answer.json()["detail"]
    assert world.starter.started == 0 and current(world) == IDLE and world.site.requests == []


def test_an_unknown_track_is_a_400_too(world):
    answer = world.post("/downloads", {"tracks": ["common-core", "nope"]})
    assert answer.status_code == 400 and "unknown track 'nope'" in answer.json()["detail"]
    assert world.starter.started == 0


def test_without_a_saved_session_it_is_a_400_that_says_to_log_in_on_your_computer(tmp_path):
    world = make_world(tmp_path, session=False)
    answer = world.post("/downloads", COMMON_CORE)
    assert answer.status_code == 400 and answer.json() == {"detail": "no saved session: run `make samples-login` on your computer"}
    assert world.starter.started == 0 and current(world) == IDLE


def test_a_session_the_intra_turned_down_is_a_400_with_the_reason_and_nothing_starts(world):
    world.site.logged_in = False
    answer = world.post("/downloads", COMMON_CORE)
    assert answer.status_code == 400
    assert answer.json()["detail"] == ("the saved session is not usable (not logged in (redirected to the sign-in page)): "
                                       "run `make samples-login` on your computer")
    assert world.starter.started == 0 and current(world) == IDLE
    assert [u for u in world.site.requests if "/projects/42cursus" in u or "/projects/cpp" in u] == []       # (no project page was asked for)
