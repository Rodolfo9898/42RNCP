"""The requests for claude: the review of what the checks did not cover, and the fixes of what the review found."""

from shared.constants import TERMINAL_REPORTS_ROOT, TERMINAL_SUBJECTS_ROOT
from tests.verdict.api.support import new_session, prepared_session, run_to_completion
from verdict.gateways.terminal import NullTerminal


def test_the_review_prompt_hands_the_subject_pdfs_to_the_terminal_where_the_editor_starts_claude(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "rp0")
    run_to_completion(c, sid)
    harness.terminal.calls.clear()
    assert c.get(f"/api/sessions/{sid}/prompts/review").status_code == 200
    assert harness.terminal.of("put_subjects") == [("put_subjects", sid)]
    assert sorted(harness.terminal.held[sid]) == ["en.norm.pdf", "push_swap.pdf"]
    assert all(data.startswith(b"%PDF") for data in harness.terminal.held[sid].values())
    c.get(f"/api/sessions/{sid}/prompts/review")
    assert len(harness.terminal.of("put_subjects")) == 1                              # (it already has exactly these: nothing is sent again)


def test_the_fix_prompt_hands_nothing_over(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "rp0b")
    run_to_completion(c, sid)
    harness.terminal.calls.clear()
    assert c.get(f"/api/sessions/{sid}/prompts/fix").status_code == 200
    assert harness.terminal.calls == []


def test_review_prompt_reflects_this_sessions_results(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "rp1")
    refused = c.get(f"/api/sessions/{sid}/prompts/review")
    assert refused.status_code == 400 and refused.json()["detail"] == "run the checks first"             # nothing was checked yet
    run_to_completion(c, sid)
    data = c.get(f"/api/sessions/{sid}/prompts/review").json()
    assert set(data) == {"text", "items", "passed", "failed", "not_run", "chars", "docker_files"}
    assert data["items"] > 0 and data["chars"] == len(data["text"]) and data["failed"] == 2 and data["passed"] == 3
    assert "A. Requirements from the subject that need judgement" in data["text"] and "project: ps." in data["text"]
    assert "Failed:" in data["text"] and "Do not edit any other file" in data["text"]


def test_asking_for_the_review_prompt_stores_the_numbering_and_the_context_it_was_asked_for(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "rp1b")
    run_to_completion(c, sid)
    session = harness.store.get(sid)
    assert session.review_items == [] and session.review_context == ""
    data = c.get(f"/api/sessions/{sid}/prompts/review").json()
    assert len(session.review_items) == data["items"] and session.review_context == harness.context.of(session)
    assert '"review_items"' in (harness.settings.workspace / sid / "session.json").read_text() and session.review_items[0].n == 1


def test_fix_prompt_is_built_from_what_this_session_found(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "fp1")
    assert c.get(f"/api/sessions/{sid}/prompts/fix").status_code == 400                # nothing was checked yet
    assert c.get("/api/sessions/nope/prompts/fix").status_code == 404
    state = run_to_completion(c, sid)
    data = c.get(f"/api/sessions/{sid}/prompts/fix").json()
    assert set(data) == {"text", "must_fix", "look_at", "bonus", "issues", "chars"}
    failed = [r for r in state["results"] if r["status"] == "fail" and r["section"] == "mandatory"]
    assert failed and data["must_fix"] == len(failed)                                 # no reviewer yet: lacking = the failed checks
    assert data["issues"] == data["must_fix"] + data["look_at"] + data["bonus"] and data["chars"] == len(data["text"])
    assert "project: ps." in data["text"] and "A. MUST FIX" in data["text"] and "Do not edit verdict.md" in data["text"]
    assert failed[0]["title"] in data["text"]
    assert "Not reviewed yet" not in data["text"]                                    # unjudged requirements are not issues


def test_the_review_prompt_lists_the_students_docker_files(client):
    c, harness = client
    sid, repo = prepared_session(c, harness, "dk1")
    (repo / "Dockerfile").write_text("FROM debian\n")
    (repo / "srcs").mkdir()
    (repo / "srcs" / "docker-compose.yml").write_text("services: {}\n")
    run_to_completion(c, sid)
    data = c.get(f"/api/sessions/{sid}/prompts/review").json()
    assert data["docker_files"] == ["Dockerfile", "srcs/docker-compose.yml"]
    assert "The student ships Docker files: Dockerfile, srcs/docker-compose.yml." in data["text"]
    assert "Start by confirming the environment" in data["text"] and "`docker info`" in data["text"]


def test_without_docker_files_claude_is_told_to_use_make(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "dk2")
    run_to_completion(c, sid)
    data = c.get(f"/api/sessions/{sid}/prompts/review").json()
    assert data["docker_files"] == [] and "No Dockerfile or compose file was found" in data["text"]


def test_the_review_prompt_points_claude_at_the_pdfs(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs4")
    run_to_completion(c, sid)
    text = c.get(f"/api/sessions/{sid}/prompts/review").json()["text"]
    assert f"in {TERMINAL_SUBJECTS_ROOT}/{sid} (" in text and "push_swap.pdf" in text and "$SUBJECTS_DIR" in text


def test_both_prompts_tell_claude_where_its_report_goes(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "ow6")
    run_to_completion(c, sid)
    report = f"`{TERMINAL_REPORTS_ROOT}/{sid}/claude-review.md`"                      # outside the project, so it never becomes one of its files
    assert report in c.get(f"/api/sessions/{sid}/prompts/review").json()["text"]
    assert report in c.get(f"/api/sessions/{sid}/prompts/fix").json()["text"]


def test_a_prompt_is_still_given_when_the_terminal_cannot_take_the_pdfs(client, make_client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "rp4")
    run_to_completion(c, sid)
    harness.terminal.down = True
    assert c.get(f"/api/sessions/{sid}/prompts/review").status_code == 200            # a terminal without the PDFs still works
    other, other_harness = make_client(terminal=NullTerminal())
    other_sid, _ = prepared_session(other, other_harness, "rp4b")
    run_to_completion(other, other_sid)
    assert other.get(f"/api/sessions/{other_sid}/prompts/review").status_code == 200


def test_a_session_without_a_project_has_no_prompt(client):
    c, _ = client
    sid = new_session(c)
    assert c.get(f"/api/sessions/{sid}/prompts/review").status_code == 400
    assert c.get(f"/api/sessions/{sid}/prompts/fix").status_code == 400
