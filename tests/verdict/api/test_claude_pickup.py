"""Every pass of claude's review reaches the verdict by itself: the editor asks (`PUT claude-review {"force": false}`), nothing is forced."""

import pytest

from tests.verdict.api.support import (REVIEW, new_session, prepared_session, put_claude, run_to_completion, session_with_claudes_report,
                                       structured_review)


def test_every_pass_of_claudes_review_is_merged_when_the_editor_asks_and_nothing_is_forced(client):
    c, harness = client
    sid, repo, first = session_with_claudes_report(c, harness, "co1")
    assert "note for 1" not in (repo / "verdict.md").read_text()
    picked = put_claude(c, sid).json()
    assert picked["new"] is True and picked["stale"] is False and picked["structured"] is True and picked["assessed"] == picked["total"] > 0
    assert picked["verdict_file"] == "verdict.md" and picked["written"] is True and "note for 1" in (repo / "verdict.md").read_text()
    assert harness.store.get(sid).claude_review == first

    assert put_claude(c, sid).json()["new"] is False                              # the same report again: nothing new
    numbers = [i.n for i in harness.store.get(sid).review_items]
    second = structured_review(numbers).replace("note for 1", "after the fix, note for 1").replace("pass with reservations", "ready to pass")
    harness.terminal.reports[sid] = second                                         # the next pass: claude saved the file again
    again = put_claude(c, sid).json()
    assert again["new"] is True and again["written"] is True
    document = (repo / "verdict.md").read_text()
    assert "after the fix, note for 1" in document and "decided by Claude: **ready to pass**" in document
    assert harness.store.get(sid).claude_review == second and harness.store.get(sid).claude_review_at


def test_a_report_nobody_asked_for_is_not_merged_by_the_pickup(client):
    c, harness = client
    sid, repo, _ = session_with_claudes_report(c, harness, "co2")
    harness.store.get(sid).review_context = ""                                    # no review was requested for this project as it is now
    answer = put_claude(c, sid).json()
    assert answer["new"] is False and answer["stale"] is True
    assert harness.store.get(sid).claude_review == "" and "note for 1" not in (repo / "verdict.md").read_text()
    assert put_claude(c, sid, force=True).json()["written"] is True              # forcing it is still the person's call
    assert "note for 1" in (repo / "verdict.md").read_text()


def test_a_run_after_the_review_was_asked_makes_the_old_report_stale_for_the_pickup(client):
    c, harness = client
    sid, repo, report = session_with_claudes_report(c, harness, "co3")
    assert put_claude(c, sid).json()["new"] is True
    run_to_completion(c, sid)                                                      # a new run starts from nothing
    assert harness.store.get(sid).claude_review == ""
    harness.terminal.reports[sid] = report                                         # the old terminal still has its report on disk
    late = put_claude(c, sid).json()
    assert late["new"] is False and late["stale"] is True and harness.store.get(sid).claude_review == ""
    assert "note for 1" not in (repo / "verdict.md").read_text()


def test_the_pickup_says_so_when_the_terminal_service_cannot_be_reached(client):
    c, harness = client
    sid, _, report = session_with_claudes_report(c, harness, "co4")
    harness.terminal.down = True
    down = put_claude(c, sid)
    assert down.status_code == 503 and down.json()["detail"] == "could not reach the terminal service"      # not "nothing new": the editor looks again
    harness.terminal.down = False
    harness.terminal.reports.clear()
    assert put_claude(c, sid).json()["new"] is False
    assert put_claude(c, "nosuchsession").status_code == 404


def test_a_report_is_not_picked_up_before_any_review_was_asked_for(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "co5")
    run_to_completion(c, sid)
    harness.terminal.reports[sid] = REVIEW                                         # (no prompt was ever asked for: nothing was requested)
    answer = put_claude(c, sid).json()
    assert (answer["new"], answer["written"], answer["stale"]) == (False, False, True)
    assert harness.store.get(sid).claude_review == "" and harness.terminal.of("report") == []     # (it is not even read)


def test_a_pickup_that_finds_nothing_still_keeps_verdict_md_current(client):
    c, harness = client
    sid, repo, _ = session_with_claudes_report(c, harness, "co6")
    put_claude(c, sid)
    (repo / "verdict.md").unlink()
    again = put_claude(c, sid).json()
    assert again["new"] is False and again["written"] is True and (repo / "verdict.md").is_file()


def test_a_pickup_that_stored_nothing_has_no_warning(client):
    c, harness = client
    sid = new_session(c)
    answer = put_claude(c, sid).json()
    assert answer["new"] is False and answer["written"] is False and answer["warning"] == ""
