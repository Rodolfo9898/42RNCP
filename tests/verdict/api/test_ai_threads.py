"""The AI review as it really runs, in a thread of its own: its progress can be read while it works, and it can be cancelled while a
request to the model hangs. These are the tests where concurrency is the point (the rest use a synchronous `spawn`)."""

import threading
import time

import pytest

from tests.verdict.api.ai_fakes import MODEL, FakeAnthropic, use_model
from tests.verdict.api.support import manual_ids, prepared_session


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")


def wait_for(c, sid, done, what, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = c.get(f"/api/sessions/{sid}").json()
        if done(state):
            return state
        time.sleep(0.05)
    raise AssertionError(f"{what} did not finish")


def checked_session(c, harness, name):
    """A session whose checks ran (in their own thread, as in the app)."""
    sid, repo = prepared_session(c, harness, name)
    assert c.post(f"/api/sessions/{sid}/runs").status_code == 202
    return sid, repo, wait_for(c, sid, lambda s: s["state"] != "running", "the run")


def wait_ai(c, sid):
    return wait_for(c, sid, lambda s: s["ai"]["state"] != "running", "the AI review")


def test_a_run_in_its_own_thread_ends_in_a_verdict(threaded_client):
    c, harness = threaded_client
    sid, repo, state = checked_session(c, harness, "th0")
    assert state["state"] == "done" and state["results"] and (repo / "verdict.md").is_file()


def test_progress_is_visible_while_the_review_runs_and_kept_afterwards(threaded_client, monkeypatch):
    c, harness = threaded_client
    sid, _, state = checked_session(c, harness, "pg1")
    inner = FakeAnthropic(manual_ids(state))
    gate, reached = threading.Event(), threading.Event()
    original = inner.parse

    def slow_parse(**kw):
        if inner.calls == 1:            # pause the second request (the manual-review one)
            reached.set()
            gate.wait(10)
        return original(**kw)

    inner.parse = slow_parse
    use_model(monkeypatch, inner)
    c.post(f"/api/sessions/{sid}/ai-review")
    assert reached.wait(10)
    mid = c.get(f"/api/sessions/{sid}").json()["ai"]
    texts = [e["text"] for e in mid["progress"]]
    assert mid["state"] == "running" and mid["started_at"]
    assert texts[0].startswith(f"Starting the AI review with {MODEL} via api.anthropic.com")
    assert any(t.startswith("Prepared ") for t in texts) and any("Step 1" in t for t in texts)
    assert any(t.startswith("Overview ready") for t in texts)
    assert mid["step"].startswith("Step 2") or "Asking" in mid["step"]
    gate.set()
    done = wait_ai(c, sid)["ai"]
    assert done["state"] == "done" and done["step"] == ""
    assert done["progress"][-1]["text"].startswith("Done: ")
    assert [e["at"] for e in done["progress"]] == sorted(e["at"] for e in done["progress"])


def test_cancel_stops_the_review_and_a_late_result_is_discarded(threaded_client, monkeypatch):
    c, harness = threaded_client
    sid, repo, before = checked_session(c, harness, "pg2")
    inner = FakeAnthropic(manual_ids(before))
    gate, reached = threading.Event(), threading.Event()
    original = inner.parse

    def hanging_parse(**kw):
        reached.set()
        gate.wait(10)                    # a server that never answers (until the test lets go)
        return original(**kw)

    inner.parse = hanging_parse
    use_model(monkeypatch, inner)
    c.post(f"/api/sessions/{sid}/ai-review")
    assert reached.wait(10)
    start = time.monotonic()
    cancelled = c.delete(f"/api/sessions/{sid}/ai-review").json()["ai"]
    assert time.monotonic() - start < 2           # does not wait for the hanging request
    assert cancelled["state"] == "cancelled" and cancelled["message"] == "Stopped by you."
    assert cancelled["progress"][-1]["text"] == "Stopped by you"
    gate.set()                                     # the abandoned request now "answers"
    time.sleep(0.5)
    after = c.get(f"/api/sessions/{sid}").json()
    assert after["ai"]["state"] == "cancelled" and after["ai"]["overview"] is None
    assert not [i for i in after["improvements"] if i["source"] == "ai"]
    assert "What is in the repository (AI)" not in (repo / "verdict.md").read_text()
    inner.parse = original                         # and a fresh review can be started straight away
    assert c.post(f"/api/sessions/{sid}/ai-review").status_code == 202
    assert wait_ai(c, sid)["ai"]["state"] == "done"

