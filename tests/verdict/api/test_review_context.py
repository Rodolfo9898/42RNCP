"""A review belongs to one repository, commit and set of subjects (and to one run): made for another context, it is dropped."""

import json
import threading

from tests.conftest import SUBJECT_PAGES, make_pdf
from tests.verdict.api.support import REVIEW, assert_no_review, attach_repo, put_claude, reviewed_session, run_to_completion
from verdict.core.models import AIState, ClaudeReport, ReviewItem
from verdict.sessions.context import ReviewContext
from verdict.sessions.store import RepoMeta, Session, Subject


def test_a_review_does_not_survive_the_next_run_even_for_the_same_project(client):
    c, harness = client
    sid, repo = reviewed_session(c, harness, "ctx0")
    run_to_completion(c, sid)
    assert harness.store.get(sid).claude_review == "" and "Claude's review" not in (repo / "verdict.md").read_text()
    assert_no_review(c, harness, sid)


def test_another_repository_never_inherits_the_previous_review(client):
    c, harness = client
    sid, _ = reviewed_session(c, harness, "ctx1")
    other = attach_repo(harness, sid, "ctx1-next")                          # the next project, in the same session
    (other / "Makefile").write_text("all:\n")
    (other / "main.c").write_text("int main(void)\n{\n\treturn (0);\n}\n")
    c.get(f"/api/sessions/{sid}")
    assert_no_review(c, harness, sid)
    run_to_completion(c, sid)
    assert "Claude's review" not in (other / "verdict.md").read_text()


def test_the_verdict_of_the_project_stops_saying_what_was_reviewed_for_another_context(client):
    c, harness = client
    sid, repo = reviewed_session(c, harness, "ctx1b")
    harness.store.get(sid).repo.commit = "def5678"                           # the project moved on (a pull, a new clone of it)
    c.get(f"/api/sessions/{sid}")
    assert_no_review(c, harness, sid)
    assert "Claude's review" not in (repo / "verdict.md").read_text()          # (the file says what the app says)


def test_other_subjects_never_inherit_the_previous_review(client):
    c, harness = client
    sid, _ = reviewed_session(c, harness, "ctx2")
    c.post("/api/library/post-common-core/subjects", files=[("files", ("ft_turing.pdf", make_pdf(SUBJECT_PAGES), "application/pdf"))])
    assert c.post(f"/api/sessions/{sid}/subjects", json={"paths": ["post-common-core/ft_turing.pdf"]}).status_code == 200
    assert_no_review(c, harness, sid)


def test_a_terminal_opened_for_the_old_project_cannot_bring_its_report_back(client):
    c, harness = client
    sid, _ = reviewed_session(c, harness, "ctx3")
    session = harness.store.get(sid)
    old_context = harness.context.of(session)
    attach_repo(harness, sid, "ctx3-next")
    c.get(f"/api/sessions/{sid}")
    harness.terminal.reports[sid] = REVIEW                                  # the old terminal still holds its report
    assert harness.claude.collect(session, old_context) is False
    assert_no_review(c, harness, sid)
    assert put_claude(c, sid).json()["new"] is False


def test_a_review_saved_before_contexts_were_recorded_is_dropped(client):
    c, harness = client
    sid, _ = reviewed_session(c, harness, "ctx4")
    harness.store.get(sid).review_context = ""                                # as in a session.json from an earlier version
    c.get(f"/api/sessions/{sid}")
    assert_no_review(c, harness, sid)


def test_a_review_dropped_on_reading_is_saved_dropped(client):
    c, harness = client
    sid, _ = reviewed_session(c, harness, "ctx5")
    harness.store.get(sid).review_context = ""
    c.get(f"/api/sessions/{sid}")
    saved = json.loads((harness.settings.workspace / sid / "session.json").read_text())
    assert saved["claude_review"] == "" and saved["review_items"] == [] and saved["claude"]["structured"] is False


# ---------------------------------------------------------------- the context itself


def session_of(repo=("git@example.com:a/b.git", "ps", "abc"), subjects=("a.pdf",), runs=0):
    session = Session(id="abcdef", created="now", runs=runs)
    session.repo = RepoMeta(url=repo[0], path=repo[1], commit=repo[2]) if repo else None
    session.subjects = {name: Subject(name=name) for name in subjects}
    return session


def test_the_context_changes_with_the_repository_the_commit_the_subjects_and_the_run():
    context = ReviewContext(threading.RLock())
    base = context.of(session_of())
    assert context.of(session_of()) == base
    for other in (session_of(repo=("git@example.com:a/b.git", "ps", "def")), session_of(repo=("git@example.com:a/c.git", "ps", "abc")),
                  session_of(repo=("git@example.com:a/b.git", "other", "abc")), session_of(repo=None), session_of(subjects=("a.pdf", "b.pdf")),
                  session_of(runs=1)):
        assert context.of(other) != base
    assert context.of(session_of(subjects=("a.pdf", "b.pdf"))) == context.of(session_of(subjects=("b.pdf", "a.pdf")))     # (their order does not matter)


def test_the_norm_is_not_part_of_the_context_because_it_follows_the_repository():
    context = ReviewContext(threading.RLock())
    with_norm = session_of()
    with_norm.subjects["en.norm.pdf"] = Subject(name="en.norm.pdf", kind="norm")
    assert context.of(with_norm) == context.of(session_of())


def test_a_review_is_dropped_only_when_there_is_one_and_it_is_for_another_context():
    dropped = []
    context = ReviewContext(threading.RLock(), on_drop=dropped.append)
    session = session_of()
    assert context.drop_stale(session) is False and dropped == []                  # nothing to drop
    session.claude_review, session.review_items, session.review_context = "text", [ReviewItem(n=1, text="x")], context.of(session)
    assert context.drop_stale(session) is False and session.claude_review == "text"      # made for this very context
    session.repo.commit = "def"
    assert context.drop_stale(session) is True and dropped == ["abcdef"]            # (a running AI review of the old context is told to stop)
    assert (session.claude_review, session.claude_review_at, session.review_items, session.review_context) == ("", "", [], "")
    assert session.claude == ClaudeReport() and session.ai == AIState(job=1)


def test_an_ai_review_of_another_context_is_dropped_too_and_a_later_job_is_ignored():
    context = ReviewContext(threading.RLock())
    session = session_of()
    session.ai, session.review_context = AIState(state="done", job=3), "[]"
    assert context.drop_stale(session) is True and (session.ai.state, session.ai.job) == ("idle", 4)
