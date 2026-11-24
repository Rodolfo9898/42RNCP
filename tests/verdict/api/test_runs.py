"""▶ Run checks: what a run needs, what it does to the session, and that it builds in a copy and never in the project."""

import json
import shutil
import subprocess

import pytest

from tests.conftest import GOOD_MAKEFILE, MAIN_C, LocalSandbox
from tests.verdict.api.support import NORM, attach_repo, new_session, prepared_session, run_to_completion
from verdict.core.models import CheckResult
from verdict.gateways.sandbox import Sandbox
from verdict.runs.workcopy import WorkCopy


def test_a_run_needs_a_repository_and_a_subject(client):
    c, harness = client
    sid = new_session(c)
    first = c.post(f"/api/sessions/{sid}/runs")
    assert first.status_code == 400 and first.json()["detail"] == "clone a repository first"
    attach_repo(harness, sid, "nothing-to-check")
    second = c.post(f"/api/sessions/{sid}/runs")
    assert second.status_code == 400 and second.json()["detail"] == "add at least one subject PDF first"
    assert c.get(f"/api/sessions/{sid}").json()["state"] == "idle"


def test_a_run_is_accepted_at_once_and_ends_in_a_verdict(client, spawn):
    c, harness = client
    sid, repo = prepared_session(c, harness, "run-test")
    spawn.hold()                                                # the checks do not start until the test lets them
    started = c.post(f"/api/sessions/{sid}/runs")
    assert started.status_code == 202
    assert (started.json()["state"], started.json()["message"], started.json()["results"]) == ("running", "git pull…", [])
    assert harness.store.get(sid).runs == 1
    spawn.release()
    state = c.get(f"/api/sessions/{sid}").json()
    assert state["state"] == "done" and state["results"]
    assert state["summary"]["overall"] == "FAIL"                # no *.h, Makefile lacks rules
    assert json.loads((harness.settings.workspace / sid / "session.json").read_text())["state"] == "done"
    assert not (harness.settings.workspace / sid / "work").exists() and (repo / "verdict.md").is_file()


def test_the_verdict_is_served_as_markdown_and_downloaded_on_request(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "export")
    run_to_completion(c, sid)
    md = c.get(f"/api/sessions/{sid}/verdict.md")
    assert md.status_code == 200 and md.headers["content-type"] == "text/markdown; charset=utf-8"
    assert "# Verdict" in md.text[:60] and "❌ **FAIL**" in md.text
    assert "content-disposition" not in md.headers
    assert 'attachment; filename="verdict.md"' == c.get(f"/api/sessions/{sid}/verdict.md", params={"download": "true"}).headers["content-disposition"]
    assert "content-security-policy" in {k.lower() for k in md.headers}


def test_run_applies_the_norm_to_c_projects(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "norm-run")
    state = run_to_completion(c, sid)
    titles = [r["title"] for r in state["results"]]
    assert "Norm rule norminette cannot check" in titles
    norm_rule = next(r for r in state["results"] if r["title"] == "Passes norminette")
    assert {s["pdf"] for s in norm_rule["sources"]} == {"push_swap.pdf", NORM}
    assert NORM in [s["name"] for s in state["subjects"]]


def test_running_again_starts_from_nothing_and_never_counts_its_own_verdict(client):
    c, harness = client
    sid, repo = prepared_session(c, harness, "again")
    first = run_to_completion(c, sid)
    second = run_to_completion(c, sid)
    assert harness.store.get(sid).runs == 2 and len(second["results"]) == len(first["results"])
    assert not any("verdict.md" in e["file"] for r in second["results"] for e in r["evidence"])
    assert [r["title"] for r in second["results"]] == [r["title"] for r in first["results"]]


def test_a_run_whose_project_has_vanished_ends_in_an_error_and_leaves_nothing_behind(client):
    c, harness = client
    sid, repo = prepared_session(c, harness, "vanished")
    shutil.rmtree(repo)
    state = run_to_completion(c, sid)
    assert state["state"] == "error" and "FileNotFoundError" in state["message"]
    assert not (harness.settings.workspace / sid / "work").exists()
    assert c.post(f"/api/sessions/{sid}/runs").status_code == 202                  # an error does not block the next run


def test_the_checks_run_in_the_sandbox_with_subjects_dir(make_client, monkeypatch):
    seen = []
    monkeypatch.setattr("verdict.runs.service.run_checks", lambda ctx, emit: seen.append(ctx))
    c, harness = make_client(sandbox=Sandbox("http://sandbox:8001"))
    sid, _ = prepared_session(c, harness, "pdfs3")
    run_to_completion(c, sid)
    folder = harness.settings.workspace / sid / "subjects"
    assert seen[0].sandbox.env == {"SUBJECTS_DIR": str(folder)} and (folder / "push_swap.pdf").is_file()
    assert harness.sandbox.env == {}                                                # the shared client is not changed: each run has its own
    assert seen[0].repo == (harness.settings.workspace / sid / "work").resolve()    # in the disposable copy, never in the project


def test_without_a_sandbox_the_checks_get_none(client, monkeypatch):
    seen = []
    monkeypatch.setattr("verdict.runs.service.run_checks", lambda ctx, emit: seen.append(ctx))
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs3b")
    assert harness.sandbox is None and run_to_completion(c, sid)["state"] == "done"
    assert seen[0].sandbox is None


def test_building_never_touches_the_clone_so_nothing_looks_committed_that_was_not(make_client):
    if not (shutil.which("make") and shutil.which("cc")):
        pytest.skip("needs make and cc")
    c, harness = make_client(sandbox=LocalSandbox())
    sid, repo = prepared_session(c, harness, "pristine")
    (repo / "Makefile").write_text(GOOD_MAKEFILE)
    (repo / "main.c").write_text(MAIN_C)
    (repo / "push_swap.h").write_text("#ifndef PUSH_SWAP_H\n# define PUSH_SWAP_H\n#endif\n")
    committed = sorted(p.name for p in repo.iterdir())
    for attempt in range(2):                                   # the second run used to see the first run's leftovers
        state = run_to_completion(c, sid)
        built = next(r for r in state["results"] if "`push_swap`" in r["title"])
        assert built["status"] == "pass", built                                    # it really was built...
        artifacts = next(r for r in state["results"] if r["title"] == "Repository contains no build artifacts")
        assert artifacts["status"] == "pass", (attempt, artifacts)                 # ...without anything appearing in the clone
        assert sorted(p.name for p in repo.iterdir() if p.name != "verdict.md") == committed
    assert not (harness.settings.workspace / sid / "work").exists()        # the disposable copy is removed afterwards
    assert not any(p.suffix == ".o" for p in repo.rglob("*"))


def test_the_sandbox_copy_is_a_git_repository_without_hooks(client):
    c, harness = client
    sid = new_session(c)
    clone = attach_repo(harness, sid, "gitcopy")
    (clone / "main.c").write_text("int main(void){return 0;}\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(clone)]
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    subprocess.run(git + ["add", "main.c"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "first"], check=True)
    (clone / ".git" / "hooks" / "post-checkout").write_text("#!/bin/sh\nexit 1\n")
    work = WorkCopy(harness.settings.workspace).make(harness.store.get(sid), clone)
    assert work == harness.settings.workspace / sid / "work"
    assert (work / ".git" / "HEAD").is_file() and not (work / ".git" / "hooks").exists()
    log = subprocess.run(["git", "-C", str(work), "log", "--format=%s"], capture_output=True, text=True, check=True)
    assert log.stdout.strip() == "first"
    (work / "leftover").write_text("x")
    assert not (WorkCopy(harness.settings.workspace).make(harness.store.get(sid), clone) / "leftover").exists()     # always made afresh
    WorkCopy.remove(work)
    assert not work.exists()


def test_results_arrive_one_by_one_while_the_checks_run(client, monkeypatch):
    c, harness = client
    sid, _ = prepared_session(c, harness, "stream")
    seen = []

    def checks(ctx, emit):
        for n in (1, 2):
            emit(CheckResult(rule_id=f"r{n}", title=f"check {n}", status="pass"))
            seen.append([r["title"] for r in c.get(f"/api/sessions/{sid}").json()["results"]])

    monkeypatch.setattr("verdict.runs.service.run_checks", checks)
    run_to_completion(c, sid)
    assert seen == [["check 1"], ["check 1", "check 2"]]
