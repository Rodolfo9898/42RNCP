"""Which project a review is about: cloned from GitHub (only over SSH, into a folder of the projects folder) or already there."""

import json

import pytest

from tests.verdict.api.support import a_result, new_session
from verdict.repository import repo as repo_mod
from verdict.repository.repo import RepoError, RepoInfo
from verdict.sessions.store import RepoMeta


def attach(c, sid, **source):
    return c.put(f"/api/sessions/{sid}/repo", json=source)


def clone_into(dest, url, commit="abc1234"):
    dest.mkdir(parents=True)
    (dest / "main.c").write_text("int main(void){}\n")
    return RepoInfo(url=url, commit=commit, subject="init", author="me")


@pytest.mark.parametrize("url", [
    "https://github.com/a/b", "http://github.com/a/b", "file:///etc/passwd", "git://github.com/a/b",
    "git@github.com:a/b; rm -rf /", "git@github.com:../../etc/passwd", "ssh://git@github.com/a/../b",
    "-oProxyCommand=evil", "git@-oProxyCommand=evil:a/b", "-ogit@github.com:a/b", "ssh://-oProxyCommand=x@host/a/b",
    "ssh://git@host:99999999/a/b", "git@github.com:a/b c", "git@github.com:", "",
])
def test_clone_rejects_unsafe_or_non_ssh_urls(client, monkeypatch, url):
    c, _ = client
    sid = new_session(c)
    monkeypatch.setattr(repo_mod, "clone", lambda *a: pytest.fail("must not clone"))
    assert attach(c, sid, kind="clone", url=url).status_code == 400


def test_clone_validates_name_and_destination_before_touching_git(client, monkeypatch):
    c, _ = client
    sid = new_session(c)
    calls = []
    monkeypatch.setattr(repo_mod, "clone", lambda *a, **k: calls.append(a))
    url = "git@github.com:user/repo.git"
    for body in ({"destination": "../../etc"}, {"destination": "/etc"}, {"name": "../evil"}, {"name": "a b"}):
        assert attach(c, sid, kind="clone", url=url, **body).status_code == 400
    assert calls == []
    assert c.get(f"/api/sessions/{sid}").json()["state"] == "idle"


def test_clone_uses_chosen_name_and_destination(client, monkeypatch):
    c, harness = client
    sid = new_session(c)
    seen = {}

    def fake_clone(url, dest, known_hosts):
        seen.update(url=url, dest=dest, known_hosts=known_hosts, state=harness.store.get(sid).state)
        return clone_into(dest, url)

    monkeypatch.setattr(repo_mod, "clone", fake_clone)
    r = attach(c, sid, kind="clone", url="git@github.com:user/repo.git", name="my-ps", destination="42/common-core")
    assert r.status_code == 200
    view = r.json()
    assert view["repo"]["path"] == "42/common-core/my-ps" and view["repo"]["name"] == "my-ps" and view["repo"]["commit"] == "abc1234"
    assert view["state"] == "idle" and view["results"] == []
    assert seen["dest"] == harness.settings.projects / "42" / "common-core" / "my-ps"
    assert seen["known_hosts"] == harness.settings.workspace / "known_hosts" and seen["state"] == "cloning"      # (the status says so while it runs)
    assert (harness.settings.projects / "42" / "common-core" / "my-ps" / "main.c").is_file()
    assert "42/common-core" in c.get("/api/projects").json()["folders"]
    again = attach(c, sid, kind="clone", url="git@github.com:user/repo.git", name="my-ps", destination="42/common-core")     # never overwrite
    assert again.status_code == 400 and "already exists" in again.json()["detail"]


def test_clone_defaults_the_name_from_the_url(client, monkeypatch):
    c, _ = client
    sid = new_session(c)
    monkeypatch.setattr(repo_mod, "clone", lambda url, dest, known_hosts: clone_into(dest, url))
    r = attach(c, sid, kind="clone", url="git@github.com:user/push_swap.git")
    assert r.json()["repo"]["path"] == "push_swap" and r.json()["repo"]["name"] == "push_swap"


def test_a_clone_that_fails_is_explained_and_can_be_tried_again(client, monkeypatch):
    c, harness = client
    sid = new_session(c)

    def refuse(url, dest, known_hosts):
        raise RepoError("Permission denied (publickey).")

    monkeypatch.setattr(repo_mod, "clone", refuse)
    failed = attach(c, sid, kind="clone", url="git@github.com:user/repo.git")
    assert failed.status_code == 400 and failed.json() == {"detail": "Permission denied (publickey)."}
    view = c.get(f"/api/sessions/{sid}").json()
    assert (view["state"], view["message"], view["repo"]) == ("error", "Permission denied (publickey).", None)
    assert json.loads((harness.settings.workspace / sid / "session.json").read_text())["state"] == "error"      # (it is on disk too)
    monkeypatch.setattr(repo_mod, "clone", lambda url, dest, known_hosts: clone_into(dest, url))
    ok = attach(c, sid, kind="clone", url="git@github.com:user/repo.git")
    assert ok.status_code == 200 and (ok.json()["state"], ok.json()["message"]) == ("idle", "")


def test_a_new_repository_forgets_the_results_of_the_previous_one(client, monkeypatch):
    c, harness = client
    sid = new_session(c)
    session = harness.store.get(sid)
    session.repo, session.results, session.state = RepoMeta(url="", commit="", path="old"), [a_result()], "done"
    monkeypatch.setattr(repo_mod, "clone", lambda url, dest, known_hosts: clone_into(dest, url))
    r = attach(c, sid, kind="clone", url="git@github.com:user/next.git")
    assert r.json()["results"] == [] and r.json()["repo"]["path"] == "next" and r.json()["state"] == "idle"


def test_an_existing_folder_can_be_used_instead_of_cloning(client, monkeypatch):
    c, harness = client
    sid = new_session(c)
    (harness.settings.projects / "42" / "libft").mkdir(parents=True)
    (harness.settings.projects / "42" / "libft" / "ft_a.c").write_text("int a;\n")
    monkeypatch.setattr(repo_mod, "clone", lambda *a: pytest.fail("must not clone"))
    assert {"path": "42/libft", "git": False} in c.get("/api/projects").json()["existing"]
    r = attach(c, sid, kind="existing", path="42/libft")
    assert r.status_code == 200
    assert (r.json()["repo"]["path"], r.json()["repo"]["name"], r.json()["repo"]["url"]) == ("42/libft", "libft", "")
    assert (harness.settings.projects / "42" / "libft" / "ft_a.c").read_text() == "int a;\n"        # nothing copied, nothing deleted


@pytest.mark.parametrize("path", ["../x", "/etc", "nope", "", "~root", "a\\b"])
def test_using_an_existing_folder_refuses_anything_outside_the_projects_folder(client, path):
    c, _ = client
    sid = new_session(c)
    assert attach(c, sid, kind="existing", path=path).status_code == 400
    assert c.get(f"/api/sessions/{sid}").json()["repo"] is None


def test_a_symbolic_link_is_not_a_project_folder(client, tmp_path):
    c, harness = client
    sid = new_session(c)
    (tmp_path / "elsewhere").mkdir()
    (harness.settings.projects / "link").symlink_to(tmp_path / "elsewhere")
    refused = attach(c, sid, kind="existing", path="link")
    assert refused.status_code == 400 and "symbolic link" in refused.json()["detail"]
    assert "link" not in [e["path"] for e in c.get("/api/projects").json()["existing"]]


@pytest.mark.parametrize("body", [{"kind": "other", "url": "x"}, {"kind": "clone"}, {"kind": "existing"}, {"url": "git@github.com:a/b.git"}, {}])
def test_a_malformed_source_is_refused(client, body):
    c, _ = client
    sid = new_session(c)
    assert attach(c, sid, **body).status_code == 422


def test_the_projects_listing_says_where_a_clone_can_go_and_what_is_there(client):
    c, harness = client
    root = harness.settings.projects
    (root / "42" / "common-core").mkdir(parents=True)
    (root / "42" / "common-core" / "libft" / ".git").mkdir(parents=True)
    (root / ".hidden").mkdir()
    listing = c.get("/api/projects").json()
    assert listing["root"] == root.name and set(listing) == {"root", "folders", "existing"}
    assert listing["folders"] == ["42", "42/common-core"]                                   # a repository is not a place to clone into
    assert listing["existing"] == [{"path": "42", "git": False}, {"path": "42/common-core", "git": False},
                                   {"path": "42/common-core/libft", "git": True}]


def test_a_session_finds_its_project_only_inside_the_projects_folder(client, tmp_path):
    c, harness = client
    session = harness.store.get(new_session(c))
    assert harness.folders.of(session) is None                                              # no repository yet
    (harness.settings.projects / "inside").mkdir()
    (tmp_path / "outside").mkdir()
    (harness.settings.projects / "link").symlink_to(tmp_path / "outside")
    for path, expected in (("inside", harness.settings.projects / "inside"), ("../outside", None), ("link", None), ("/etc", None), ("", None)):
        session.repo = RepoMeta(url="", commit="", path=path)
        assert harness.folders.of(session) == expected, path
    assert harness.folders.relative(harness.settings.projects / "42" / "x") == "42/x"
