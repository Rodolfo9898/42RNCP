"""DELETE /downloads/current and the ways a download ends other than done: stopped, session expired, network down, no login possible."""
from __future__ import annotations

import httpx
import pytest

from tests.scraper.server.test_downloads import COMMON_CORE, current


def test_a_stop_asked_while_it_runs_is_seen_between_two_projects(world):
    world.post("/downloads", COMMON_CORE)
    assert world.delete("/downloads/current").json() == {"state": "running"}          # (it only stops when it gets to the next project)
    world.starter.run()
    stopped = current(world)
    assert stopped["state"] == "cancelled" and stopped["lines"][-1] == "Stopped on request."
    assert stopped["summary"] is None                                                 # nothing was done: nothing to sum up
    assert not (world.tmp / "samples").exists()


def test_a_stop_in_the_middle_leaves_what_was_done_and_sums_it_up(world):
    world.site.on_page["cpp-module-00"] = lambda: world.delete("/downloads/current")  # asked while the first project is being read
    world.post("/downloads", COMMON_CORE)
    world.starter.run()
    stopped = current(world)
    assert stopped["state"] == "cancelled" and "Stopped on request." in stopped["lines"]
    assert (world.tmp / "samples/common-core/cpp-modules/cpp00.pdf").is_file()        # the project in hand was finished...
    assert not (world.tmp / "samples/common-core/cpp-modules/cpp01.pdf").exists() and not (world.tmp / "samples/common-core/libft.pdf").exists()
    assert stopped["summary"] == {"downloaded_subjects": 1, "downloaded_artifacts": 1, "existing": 0, "failed": [], "no_files": []}
    assert not [line for line in stopped["lines"] if "cpp01" in line]                 # ...and the next one was never started


def test_after_a_stop_the_next_download_starts_clean_and_what_was_done_is_not_done_again(world):
    world.site.on_page["cpp-module-00"] = lambda: world.delete("/downloads/current")
    world.post("/downloads", COMMON_CORE)
    world.starter.run()
    world.site.on_page.clear()
    assert world.post("/downloads", COMMON_CORE).json()["id"] == "job-2"
    assert current(world)["lines"] == [] and current(world)["state"] == "running"
    world.starter.run()
    again = current(world)
    assert again["state"] == "done" and again["lines"][0] == "3 project(s) selected, 2 to visit."
    assert again["summary"]["downloaded_subjects"] == 2


def test_a_stop_asked_when_nothing_runs_changes_nothing(world):
    assert world.delete("/downloads/current").json() == {"state": "idle"}
    world.post("/downloads", {"projects": ["libft"]})
    world.starter.run()
    assert world.delete("/downloads/current").json() == {"state": "done"} and current(world)["state"] == "done"


def test_a_stop_asked_during_the_last_project_comes_too_late_and_the_download_is_done(world):
    world.site.on_page["42cursus-libft"] = lambda: world.delete("/downloads/current")           # libft is the last of the three
    world.post("/downloads", COMMON_CORE)
    world.starter.run()
    finished = current(world)
    assert finished["state"] == "done" and (world.tmp / "samples/common-core/libft.pdf").is_file()
    assert finished["summary"]["downloaded_subjects"] == 3 and "Stopped on request." not in finished["lines"]


# ------------------------------------------------------------------------------------------------- failures


@pytest.mark.parametrize("expires_on,subjects", [("cpp-module-00", 0), ("cpp-module-01", 1)])
def test_a_session_that_expires_during_the_run_fails_the_download_and_says_why(world, expires_on, subjects):
    world.site.on_page[expires_on] = lambda: setattr(world.site, "logged_in", False)
    world.post("/downloads", COMMON_CORE)
    world.starter.run()
    failed = current(world)
    assert failed["state"] == "failed"
    assert any("The session expired" in line for line in failed["lines"])
    assert failed["lines"][-1] == "The saved session stopped working: run `make samples-login` on your computer, then download again."
    assert not any(line.startswith("Done:") for line in failed["lines"])
    assert (failed["summary"] or {}).get("downloaded_subjects", 0) == subjects
    assert (failed["summary"] is None) == (subjects == 0)                                       # no summary when nothing was done


def test_the_service_cannot_log_in_when_the_saved_session_vanishes_after_the_check(world):
    world.post("/downloads", COMMON_CORE)                                                       # the check passes, the thread has not started
    world.settings.state_file.unlink()
    world.starter.run()
    failed = current(world)
    assert failed["state"] == "failed" and failed["summary"] is None
    assert failed["lines"][-1] == "The downloader never logs in to the 42 intra: run `make samples-login` on your computer, then try again."
    assert [url for url in world.site.requests if "signin" in url] == []                       # no login page was ever asked for


def test_the_intra_going_away_between_the_check_and_the_run_is_a_failed_download_not_a_dead_thread(world):
    asked = []
    original = world.site.handler

    def goes_down_after_the_first_check(request):
        if request.url.path == "/projects/list":
            asked.append(1)
            if len(asked) > 1:
                raise httpx.ConnectError("name resolution failed")
        return original(request)

    world.site.handler = goes_down_after_the_first_check
    world.post("/downloads", COMMON_CORE)
    world.starter.run()
    failed = current(world)
    assert failed["state"] == "failed" and failed["lines"][-1] == "Network error: name resolution failed"
    assert failed["summary"] is None
    world.site.handler = original                                                                # the intra is back: the service is free again
    assert world.post("/downloads", {"projects": ["libft"]}).status_code == 202
