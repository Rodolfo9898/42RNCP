"""Every run starts fresh: claude's saved report deleted, the old verdict removed, every review forgotten, a running AI review stopped."""

from tests.verdict.api.support import REVIEW, prepared_session, put_claude, run_to_completion, session_with_claudes_report
from verdict.core.models import AIState
from verdict.gateways.terminal import NullTerminal
from verdict.reviews import ai as ai_mod


def prepared_with_verdict(c, harness, name):
    sid, repo = prepared_session(c, harness, name)
    run_to_completion(c, sid)
    assert (repo / "verdict.md").is_file() and harness.store.get(sid).verdict_file == "verdict.md"
    return sid, repo


def test_a_run_deletes_claudes_report_removes_the_old_verdict_and_forgets_every_review_before_anything_else(client, spawn):
    c, harness = client
    sid, repo, _ = session_with_claudes_report(c, harness, "fr1")
    assert put_claude(c, sid, force=True).status_code == 200
    session = harness.store.get(sid)
    assert session.claude_review and session.claude.structured and session.results and session.improvements
    spawn.hold()                                                                     # (the checks themselves do not start)
    first_run = session.runs
    harness.terminal.calls.clear()
    answer = c.post(f"/api/sessions/{sid}/runs").json()
    assert harness.terminal.of("delete_report") == [("delete_report", sid)] and sid not in harness.terminal.reports   # claude's saved report is gone
    assert harness.terminal.of("report") == []                                       # ... and nothing was collected from it
    assert not (repo / "verdict.md").exists() and session.verdict_file == "" and answer["verdict_file"] == ""
    assert answer["state"] == "running" and answer["results"] == [] and answer["improvements"] == [] and answer["summary"]["overall"] == "NOT RUN"
    assert answer["ai"]["reviews"] == {} and answer["ai"]["state"] == "idle" and answer["claude"]["structured"] is False
    assert session.claude_review == "" and session.claude_review_at == "" and session.review_items == [] and session.readme == {}
    assert session.runs == first_run + 1


def test_a_verdict_md_that_is_the_projects_own_is_never_removed(client, spawn):
    c, harness = client
    sid, repo = prepared_session(c, harness, "fr2")
    (repo / "verdict.md").write_text("# my own notes about verdicts\n")                # (not written by this app: no marker)
    (repo / "claude-review.md").write_text("my own file\n")
    spawn.hold()
    assert c.post(f"/api/sessions/{sid}/runs").status_code == 202
    assert (repo / "verdict.md").read_text() == "# my own notes about verdicts\n" and (repo / "claude-review.md").read_text() == "my own file\n"


def test_the_generated_verdict_files_of_any_version_are_removed_and_a_link_is_never_followed(client, spawn, tmp_path):
    c, harness = client
    sid, repo = prepared_with_verdict(c, harness, "fr3")
    marker = (repo / "verdict.md").read_text().splitlines()[0]
    (repo / "verdict-report.md").write_text(marker + "\nold\n")
    (repo / "claude-review.md").write_text(marker + "\nold review\n")
    outside = tmp_path / "outside.md"
    outside.write_text(marker + "\nnot in the project\n")
    (repo / "claude-review-report.md").symlink_to(outside)
    spawn.hold()
    c.post(f"/api/sessions/{sid}/runs")
    assert not any((repo / n).exists() for n in ("verdict.md", "verdict-report.md", "claude-review.md"))
    assert outside.exists()                                                           # (the link may point anywhere: it is left alone)


def test_a_terminal_opened_before_the_run_cannot_bring_its_report_back(client, spawn):
    c, harness = client
    sid, repo = prepared_with_verdict(c, harness, "fr4")
    session = harness.store.get(sid)
    old_context = harness.context.of(session)
    spawn.hold()
    c.post(f"/api/sessions/{sid}/runs")
    harness.terminal.reports[sid] = REVIEW                                            # the old claude saves its report after the run began
    assert harness.claude.collect(session, old_context) is False
    assert session.claude_review == "" and not (repo / "verdict.md").exists()
    assert harness.context.of(session) != old_context
    late = put_claude(c, sid).json()                                                  # (and the editor asking does not merge it either)
    assert late["new"] is False and late["stale"] is True and session.claude_review == ""


def test_a_run_stops_a_running_ai_review(client, spawn):
    c, harness = client
    sid, _ = prepared_with_verdict(c, harness, "fr5")
    job = ai_mod.Job()
    harness.jobs.add(sid, job)
    session = harness.store.get(sid)
    session.ai = AIState(state="running", job=4)
    session.review_context = harness.context.of(session)                              # (so that nothing but the run itself stops the job)
    spawn.hold()
    c.post(f"/api/sessions/{sid}/runs")
    assert job.cancel.is_set() and session.ai.state == "idle" and session.ai.job > 4      # (a running job that finishes now is ignored)
    assert harness.jobs.cancel(sid) is False                                          # and it is no longer listed


def test_a_terminal_service_that_is_down_never_stops_a_run(client, spawn):
    c, harness = client
    sid, _ = prepared_session(c, harness, "fr6")
    harness.terminal.down = True
    started = c.post(f"/api/sessions/{sid}/runs")
    assert started.status_code == 202 and harness.terminal.of("delete_report") == [("delete_report", sid)]
    assert c.get(f"/api/sessions/{sid}").json()["state"] == "done"


def test_a_run_for_a_project_with_no_terminal_configured_deletes_nothing(make_client):
    c, harness = make_client(terminal=NullTerminal())
    sid, _ = prepared_session(c, harness, "fr7")
    assert run_to_completion(c, sid)["state"] == "done"

