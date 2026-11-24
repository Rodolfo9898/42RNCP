"""The AI review through an API: started, followed, advisory and verified. The model is a fake; the work runs in the request's thread."""

import pytest

from tests.verdict.api.ai_fakes import MODEL, Broken, FakeAnthropic, use_model
from tests.verdict.api.support import manual_ids, prepared_session, run_to_completion
from verdict.ai_review.runner import AiReviewRun
from verdict.core.models import AIState
from verdict.reviews import ai
from verdict.sessions.store import Store


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")


def start(c, sid):
    return c.post(f"/api/sessions/{sid}/ai-review")


def test_ai_is_off_until_a_key_is_configured(client):
    c, harness = client
    assert c.get("/api/health").json()["llm"]["configured"] is False
    sid, _ = prepared_session(c, harness, "ai0")
    run_to_completion(c, sid)
    r = start(c, sid)
    assert r.status_code == 400 and "ANTHROPIC_API_KEY" in r.json()["detail"]
    assert c.get(f"/api/sessions/{sid}").json()["ai"]["state"] == "idle"


def test_ai_needs_the_checks_first(client, key):
    c, harness = client
    sid, _ = prepared_session(c, harness, "ai1")
    r = start(c, sid)
    assert r.status_code == 400 and r.json()["detail"] == "run the checks first"
    assert c.get(f"/api/sessions/{sid}").json()["ai"]["state"] == "idle"


def test_ai_review_end_to_end_is_advisory_and_verified(client, key, monkeypatch, spawn):
    c, harness = client
    sid, repo = prepared_session(c, harness, "ai2")
    before = run_to_completion(c, sid)
    ids = manual_ids(before)
    assert ids, "the fixture subject should leave some items for a human"
    fake = FakeAnthropic(ids)
    use_model(monkeypatch, fake)

    spawn.hold()
    started = start(c, sid)
    assert started.status_code == 202 and started.json()["ai"]["state"] == "running" and started.json()["ai"]["model"] == MODEL
    spawn.release()
    after = c.get(f"/api/sessions/{sid}").json()
    ai_state = after["ai"]
    assert ai_state["state"] == "done", ai_state["message"]
    assert fake.calls == 2 and ai_state["input_tokens"] == 2000 and ai_state["model"] == MODEL
    assert ai_state["overview"]["purpose"] == "Tiny program."
    assert set(ai_state["reviews"]) == set(ids)
    assert ai_state["reviews"][ids[0]]["evidence"] == [{"file": "main.c", "line": 3, "snippet": ""}]

    # the AI never changes the deterministic result
    assert after["results"] == before["results"]                       # the AI never rewrites a check result ...
    moved = after["summary"]["mandatory"]
    assert moved["manual"] == 0 and moved["fail"] >= before["summary"]["mandatory"]["fail"]   # ... but its answers count where verdict.md lists them
    ai_items = [i for i in after["improvements"] if i["source"] == "ai"]
    assert [i["title"] for i in ai_items] == ["main ignores arguments"]
    assert [(e["file"], e["line"]) for e in ai_items[0]["evidence"]] == [("main.c", 1)]      # ghost.c was invented

    written = (repo / "verdict.md").read_text()
    assert "## What is in the repository (AI)" in written and "advisory and unverified" in written
    ok = written[written.index("## ✅ Ok"):written.index("## Improvements")]
    assert "Requirements claude found ok" in ok and "main returns 0." in ok and "`AI`" in ok        # answered by the model, now in the ok list
    assert "_(AI)_" in written


def test_ai_failure_is_reported_without_touching_the_verdict(client, key, monkeypatch):
    c, harness = client
    sid, _ = prepared_session(c, harness, "ai3")
    before = run_to_completion(c, sid)
    use_model(monkeypatch, Broken("Rate limited by the API. Wait a minute and try again."))
    start(c, sid)
    after = c.get(f"/api/sessions/{sid}").json()
    assert after["ai"]["state"] == "error" and "Rate limited" in after["ai"]["message"]
    assert after["results"] == before["results"] and after["state"] == "done"


def test_failures_are_logged_in_the_progress(client, key, monkeypatch):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pg4")
    run_to_completion(c, sid)
    use_model(monkeypatch, Broken("The AI server's answer was empty (fields: choices)."))
    start(c, sid)
    state = c.get(f"/api/sessions/{sid}").json()["ai"]
    assert state["state"] == "error" and state["progress"][-1]["text"].startswith("Failed: The AI server's answer was empty")
    assert state["step"] == ""


def test_a_failure_nobody_foresaw_is_a_message_not_a_trace(client, key, monkeypatch, caplog):
    c, harness = client
    sid, _ = prepared_session(c, harness, "ai3b")
    run_to_completion(c, sid)
    monkeypatch.setattr(ai, "make_client", lambda **kw: 1 / 0)
    start(c, sid)
    state = c.get(f"/api/sessions/{sid}").json()["ai"]
    assert state["state"] == "error" and state["message"] == "Unexpected error during the AI review (see the server log)."
    assert "ZeroDivisionError" in caplog.text and "ZeroDivisionError" not in str(state)
    assert not harness.jobs.cancel(sid)                                          # (the job is not left listed)


def test_a_new_run_clears_stale_ai_results(client, key, monkeypatch):
    c, harness = client
    sid, _ = prepared_session(c, harness, "ai4")
    ids = manual_ids(run_to_completion(c, sid))
    use_model(monkeypatch, FakeAnthropic(ids))
    start(c, sid)
    assert c.get(f"/api/sessions/{sid}").json()["ai"]["state"] == "done"
    again = run_to_completion(c, sid)
    assert again["ai"]["state"] == "idle" and again["ai"]["reviews"] == {}
    assert not [i for i in again["improvements"] if i["source"] == "ai"]


def test_one_review_at_a_time_and_not_while_the_checks_run(client, key, monkeypatch, spawn):
    c, harness = client
    sid, _ = prepared_session(c, harness, "ai5")
    run_to_completion(c, sid)
    use_model(monkeypatch, FakeAnthropic([]))
    spawn.hold()
    assert start(c, sid).status_code == 202
    again = start(c, sid)
    assert again.status_code == 409 and again.json()["detail"] == "something is already running"
    spawn.release()
    harness.store.get(sid).state = "running"
    assert start(c, sid).status_code == 409


def test_a_review_that_was_cancelled_while_the_model_answered_is_discarded(client, key, monkeypatch):
    c, harness = client
    sid, repo = prepared_session(c, harness, "ai6")
    ids = manual_ids(run_to_completion(c, sid))
    fake = FakeAnthropic(ids)
    original = fake.parse

    def cancelled_during_the_first_request(**kw):
        if fake.calls == 0:
            assert c.delete(f"/api/sessions/{sid}/ai-review").json()["ai"]["state"] == "cancelled"
        return original(**kw)

    fake.parse = cancelled_during_the_first_request
    use_model(monkeypatch, fake)
    start(c, sid)
    after = c.get(f"/api/sessions/{sid}").json()
    assert after["ai"]["state"] == "cancelled" and after["ai"]["overview"] is None and after["ai"]["reviews"] == {}
    assert not [i for i in after["improvements"] if i["source"] == "ai"]
    assert "What is in the repository (AI)" not in (repo / "verdict.md").read_text()


def test_the_answer_of_a_review_that_was_replaced_meanwhile_is_dropped(client, key, monkeypatch):
    """Whatever replaced the state of the review (a run, another review) wins: the late answer is neither shown nor written."""
    c, harness = client
    sid, repo = prepared_session(c, harness, "ai6b")
    ids = manual_ids(run_to_completion(c, sid))
    use_model(monkeypatch, FakeAnthropic(ids))
    session = harness.store.get(sid)
    state = AIState(state="running", job=1)
    session.ai = state
    harness.jobs.add(sid, job := ai.Job())
    session.ai = AIState(job=2)                                                # (replaced before the answer comes in)
    AiReviewRun(harness.store, harness.folders, harness.document, harness.jobs, session, state, job).run()
    assert session.ai == AIState(job=2) and state.state == "running" and state.overview is None
    assert not [i for i in session.improvements if i.source == "ai"]
    assert "What is in the repository (AI)" not in (repo / "verdict.md").read_text() and harness.jobs.cancel(sid) is False


def test_cancel_without_a_running_review_changes_nothing(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pg3")
    r = c.delete(f"/api/sessions/{sid}/ai-review")
    assert r.status_code == 200 and r.json()["ai"]["state"] == "idle" and r.json()["ai"]["progress"] == []


def test_a_review_that_was_running_when_the_app_stopped_is_an_error_after_the_restart(client, key, monkeypatch, spawn):
    c, harness = client
    sid, _ = prepared_session(c, harness, "ai7")
    run_to_completion(c, sid)
    use_model(monkeypatch, FakeAnthropic([]))
    spawn.hold()
    start(c, sid)
    harness.store.save(harness.store.get(sid))                                     # (whatever saves the session while the review runs)
    after = Store(harness.settings.workspace).get(sid)                             # a new process reading what the old one saved
    assert (after.ai.state, after.ai.message) == ("error", "Interrupted by a restart.")
