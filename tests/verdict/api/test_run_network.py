"""The two steps of a run that need the network: `git pull` in the project, and the submodules in the work copy."""

import pytest

from tests.conftest import make_pdf
from tests.verdict.api.support import NORM, attach_repo, new_session, prepared_session, run_to_completion
from verdict.repository import repo as repo_mod
from verdict.repository.repo import RepoError, RepoInfo, SubmoduleNote

REMOTE = "git@example.com:a/b.git"


def pulls(monkeypatch, behaviour):
    """Replaces git pull; `behaviour(path)` returns (RepoInfo, summary) or raises RepoError. Returns the list of calls."""
    calls = []

    def fake(path, known_hosts):
        calls.append(path)
        return behaviour(path)

    monkeypatch.setattr(repo_mod, "pull", fake)
    return calls


def test_every_run_pulls_first_and_shows_what_the_pull_did(client, monkeypatch):
    c, harness = client
    sid, repo = prepared_session(c, harness, "pl1")
    seen = []

    def newer(path):
        seen.append(harness.store.get(sid).results.copy())
        return RepoInfo(url=REMOTE, commit="def5678", subject="newer", author="me"), "Fast-forward"

    calls = pulls(monkeypatch, newer)
    done = run_to_completion(c, sid)
    assert calls == [repo.resolve()] and seen == [[]]                                 # the pull came before any check produced a result
    assert done["repo"]["commit"] == "def5678" and done["repo"]["subject"] == "newer" and done["message"] == "git pull: now at def5678"
    assert done["repo"]["name"] == "ps" and done["repo"]["path"] == "pl1"              # (what the person chose stays)
    assert done["state"] == "done" and done["results"]
    again = pulls(monkeypatch, lambda path: (RepoInfo(url=REMOTE, commit="def5678", subject="newer", author="me"), "Already up to date."))
    done = run_to_completion(c, sid)
    assert len(again) == 1 and done["message"] == "git pull: already up to date (def5678)"


def test_a_pull_that_cannot_be_done_does_not_stop_the_checks(client, monkeypatch):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pl2")

    def refuse(path):
        raise RepoError("git pull failed: diverged")

    pulls(monkeypatch, refuse)
    done = run_to_completion(c, sid)
    assert done["state"] == "done" and done["results"] and done["message"] == "git pull skipped: git pull failed: diverged"
    assert done["repo"]["commit"] == "abc1234"                                        # unchanged


def test_a_project_without_a_remote_is_not_pulled(client, monkeypatch, spawn):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pl3")
    harness.store.get(sid).repo.url = ""
    calls = pulls(monkeypatch, lambda path: pytest.fail("there is nothing to pull from"))
    spawn.hold()
    assert c.post(f"/api/sessions/{sid}/runs").json()["message"] == ""                # (it does not even say it is pulling)
    spawn.release()
    state = c.get(f"/api/sessions/{sid}").json()
    assert calls == [] and state["state"] == "done" and state["message"] == ""


def test_the_status_says_it_is_pulling_while_it_does(client, spawn):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pl4")
    spawn.hold()
    assert c.post(f"/api/sessions/{sid}/runs").json()["message"] == "git pull…"
    assert c.get(f"/api/sessions/{sid}").json()["state"] == "running"


def test_the_checks_look_at_what_was_pulled(client, monkeypatch):
    c, harness = client
    sid, repo = prepared_session(c, harness, "pl5")
    seen = []

    def pull_a_file(path):
        (path / "NEW.md").write_text("arrived with the pull\n")
        return RepoInfo(url=REMOTE, commit="aaa1111", subject="s", author="a"), ""

    pulls(monkeypatch, pull_a_file)
    monkeypatch.setattr("verdict.runs.service.run_checks", lambda ctx, emit: seen.append((ctx.repo / "NEW.md").is_file()))
    run_to_completion(c, sid)
    assert seen == [True]                                                             # (the copy the checks run in has it)
    assert "aaa1111" in (repo / "verdict.md").read_text()                               # the verdict names the commit that was checked


def test_a_pull_that_brings_c_code_attaches_the_norm_before_the_checks(client, monkeypatch):
    c, harness = client
    no_lang = make_pdf(["Chapter I\nMandatory part\nYou must write a configuration file.\n"])
    c.post("/api/library/rncp/subjects", files=[("files", ("conf.pdf", no_lang, "application/pdf"))])
    sid = new_session(c)
    c.post(f"/api/sessions/{sid}/subjects", json={"paths": ["rncp/conf.pdf"]})
    repo = attach_repo(harness, sid, "pl6")
    (repo / "README.md").write_text("no code yet\n")

    def bring_c(path):
        (path / "main.c").write_text("int main(void){return 0;}\n")
        return RepoInfo(url=REMOTE, commit="c0de123", subject="adds C", author="a"), ""

    pulls(monkeypatch, bring_c)
    assert NORM not in harness.store.get(sid).subjects
    state = run_to_completion(c, sid)
    assert [s["name"] for s in state["subjects"] if s["kind"] == "norm"] == [NORM]


def test_a_run_downloads_the_submodules_into_the_copy_and_says_so(client, monkeypatch):
    c, harness = client
    sid, repo = prepared_session(c, harness, "sm1")
    (repo / ".gitmodules").write_text('[submodule "libs/libft"]\n\tpath = libs/libft\n\turl = https://github.com/Rodolfo9898/libft.git\n')
    (repo / "libs" / "libft").mkdir(parents=True)
    seen = {}

    def fake_fetch(work, known_hosts, **kw):
        seen.update(work=work, known_hosts=known_hosts, extra_hosts=kw.get("extra_hosts"), listing=sorted(p.name for p in work.iterdir()))
        return [SubmoduleNote("libs/libft", True, "downloaded at abc1234"), SubmoduleNote("libs/mlx", False, "no address")]

    monkeypatch.setattr(repo_mod, "fetch_submodules", fake_fetch)
    monkeypatch.setattr("verdict.runs.service.run_checks", lambda ctx, emit: seen.update(notes=ctx.cache.get("submodule_notes")))
    done = run_to_completion(c, sid)
    assert [(n.path, n.ok) for n in seen["notes"]] == [("libs/libft", True), ("libs/mlx", False)]                    # (so a failed build can say what was tried)
    assert seen["work"] == harness.settings.workspace / sid / "work" and seen["known_hosts"] == harness.settings.workspace / "known_hosts"
    assert seen["extra_hosts"] == {"example.com"} and ".gitmodules" in seen["listing"]                                # (the project's own host may be used too)
    assert done["state"] == "done" and "1 submodule(s) downloaded" in done["message"] and "git pull" in done["message"]
    assert list((repo / "libs" / "libft").iterdir()) == []                                                           # the project itself is untouched


def test_a_project_without_submodules_downloads_nothing(client, monkeypatch):
    c, harness = client
    sid, _ = prepared_session(c, harness, "sm2")
    monkeypatch.setattr(repo_mod, "fetch_submodules", lambda *a, **kw: pytest.fail("there are no submodules"))
    assert run_to_completion(c, sid)["state"] == "done"


def test_a_download_that_goes_wrong_never_stops_the_checks(client, monkeypatch):
    c, harness = client
    sid, repo = prepared_session(c, harness, "sm3")
    (repo / ".gitmodules").write_text('[submodule "x"]\n\tpath = libs/x\n\turl = https://github.com/a/x.git\n')
    (repo / "libs" / "x").mkdir(parents=True)

    def broken(work, known_hosts, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(repo_mod, "fetch_submodules", broken)
    seen = []
    monkeypatch.setattr("verdict.runs.service.run_checks", lambda ctx, emit: seen.append(ctx.cache["submodule_notes"]))
    done = run_to_completion(c, sid)
    assert done["state"] == "done" and "downloaded" not in done["message"]
    assert [(n.ok, n.message) for n in seen[0]] == [(False, "OSError: disk full")]      # (the build check can say what happened)
