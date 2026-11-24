"""A review: created, read, deleted, kept across restarts, and refused while it is busy."""

import pytest

from tests.verdict.api.support import attach_repo, new_session
from verdict.sessions.store import Store

VIEW_KEYS = {"id", "state", "message", "repo", "subjects", "results", "improvements", "claude", "readme", "verdict_file",
             "claude_review_at", "ai", "summary"}


def test_a_session_is_created_empty_and_read_back(client):
    c, harness = client
    created = c.post("/api/sessions")
    assert created.status_code == 201
    view = created.json()
    assert set(view) == VIEW_KEYS and view["state"] == "idle" and view["repo"] is None and view["subjects"] == []
    assert view["summary"]["overall"] == "NOT RUN" and view["ai"]["state"] == "idle" and view["claude"]["structured"] is False
    assert c.get(f"/api/sessions/{view['id']}").json() == view
    assert (harness.settings.workspace / view["id"] / "session.json").is_file()


def test_unknown_or_malformed_session_ids_are_404(client):
    c, _ = client
    assert c.get("/api/sessions/does-not-exist").status_code == 404
    assert c.get("/api/sessions/..%2f..%2fetc").status_code == 404
    for method, path in (("delete", ""), ("post", "/runs"), ("get", "/prompts/fix"), ("put", "/progress"), ("post", "/ai-review"),
                         ("delete", "/ai-review"), ("get", "/verdict.md")):
        assert getattr(c, method)(f"/api/sessions/nope{path}").status_code == 404, (method, path)
    assert c.put("/api/sessions/nope/claude-review", json={"force": False}).status_code == 404
    assert c.put("/api/sessions/nope/repo", json={"kind": "existing", "path": "x"}).status_code == 404


def test_deleting_a_session_removes_it_and_its_folder(client):
    c, harness = client
    sid = new_session(c)
    gone = c.delete(f"/api/sessions/{sid}")
    assert gone.status_code == 204 and gone.content == b""
    assert c.get(f"/api/sessions/{sid}").status_code == 404 and not (harness.settings.workspace / sid).exists()
    assert c.delete(f"/api/sessions/{sid}").status_code == 404


def test_a_session_comes_back_after_a_restart_and_one_that_was_busy_is_an_error(client, make_client):
    c, harness = client
    sid = new_session(c)
    c.post(f"/api/sessions/{sid}/subjects", json={"paths": ["common-core/push_swap.pdf"]})
    harness.store.get(sid).state = "running"
    harness.store.save(harness.store.get(sid))
    after = Store(harness.settings.workspace).get(sid)                     # a new process reading what the old one saved
    assert [s for s in after.subjects if after.subjects[s].kind == "subject"] == ["push_swap.pdf"]
    assert (after.state, after.message) == ("error", "Interrupted by a restart.")
    other, _ = make_client()
    assert other.get(f"/api/sessions/{sid}").json()["state"] == "error"


@pytest.mark.parametrize("state", ["cloning", "running"])
def test_a_busy_session_refuses_a_new_repository_and_a_new_run(client, state):
    c, harness = client
    sid = new_session(c)
    attach_repo(harness, sid, "busy")
    harness.store.get(sid).state = state
    for answer in (c.put(f"/api/sessions/{sid}/repo", json={"kind": "existing", "path": "busy"}), c.post(f"/api/sessions/{sid}/runs")):
        assert answer.status_code == 409 and answer.json()["detail"] == f"session is busy ({state})"
    assert c.get(f"/api/sessions/{sid}").json()["state"] == state

