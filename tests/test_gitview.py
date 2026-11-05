"""The Source Control view's backend: what changed in the project since its last commit, read with a git that cannot run the repository's programs."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from verdict import gitview
from verdict.gitview import GitViewError, sides, status

from .test_api import attach_repo, client  # noqa: F401  (the app fixture)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null"}


def git(root, *args):
    done = subprocess.run(["git", *args], cwd=root, env=ENV, capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "Makefile").write_text("all:\n\t@echo ok\n")
    (root / "main.c").write_text("int main(void)\n{\n\treturn (0);\n}\n")
    (root / "old.c").write_text("int old;\n")
    (root / "dir").mkdir()
    (root / "dir" / "util.c").write_text("int util;\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "first")
    return root


def files(result):
    return {f["path"]: (f["x"], f["y"], f["kind"]) for f in result["files"]}


def test_a_clean_repository_has_nothing_to_show_and_names_its_branch_and_commit(repo):
    result = status(repo)
    assert result["available"] and result["files"] == [] and result["branch"] == "main" and len(result["head"]) == 7 and result["ahead"] == result["behind"] == 0


def test_each_kind_of_change_is_told_apart(repo):
    (repo / "main.c").write_text("int main(void)\n{\n\treturn (1);\n}\n")                       # modified, not staged
    (repo / "Makefile").write_text("all:\n")
    git(repo, "add", "Makefile")                                                                # modified, staged
    (repo / "new.c").write_text("int n;\n")
    git(repo, "add", "new.c")                                                                   # added
    (repo / "old.c").unlink()                                                                   # deleted
    (repo / "dir" / "util.c").rename(repo / "dir" / "tools.c")
    git(repo, "add", "-A", "dir")                                                               # renamed
    (repo / "notes.txt").write_text("not tracked\n")
    (repo / "dir" / "deep.txt").write_text("not tracked either\n")
    result = status(repo)
    assert files(result) == {
        "main.c": ("", "M", "modified"), "Makefile": ("M", "", "modified"), "new.c": ("A", "", "added"), "old.c": ("", "D", "deleted"),
        "dir/tools.c": ("R", "", "renamed"), "notes.txt": ("?", "?", "untracked"), "dir/deep.txt": ("?", "?", "untracked"),
    }
    assert [f for f in result["files"] if f["path"] == "dir/tools.c"][0]["from"] == "dir/util.c"
    assert [f["path"] for f in result["files"]][:3] == ["Makefile", "main.c", "new.c"] or [f["path"] for f in result["files"]][0].count("/") == 0   # top level first


def test_a_conflict_is_a_conflict(repo):
    git(repo, "checkout", "-q", "-b", "other")
    (repo / "main.c").write_text("int a;\n")
    git(repo, "commit", "-qam", "other")
    git(repo, "checkout", "-q", "main")
    (repo / "main.c").write_text("int b;\n")
    git(repo, "commit", "-qam", "main")
    subprocess.run(["git", "merge", "other"], cwd=repo, env=ENV, capture_output=True)
    assert files(status(repo))["main.c"][2] == "conflict"


def test_ahead_and_behind_of_the_upstream(repo, tmp_path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    (repo / "x.c").write_text("x\n")
    git(repo, "add", "x.c")
    git(repo, "commit", "-qm", "local")
    result = status(repo)
    assert result["upstream"] == "origin/main" and (result["ahead"], result["behind"]) == (1, 0)


def test_a_folder_that_is_not_a_repository_says_so(tmp_path):
    (tmp_path / "plain").mkdir()
    result = status(tmp_path / "plain")
    assert not result["available"] and "not a git repository" in result["error"] and result["files"] == []


@pytest.mark.parametrize("setting", ["core.fsmonitor", "core.sshCommand", "filter.x.clean", "diff.x.textconv", "core.pager", "include.path", "core.worktree", "alias.st", "core.editor"])
def test_git_is_not_run_when_the_repository_names_a_program_for_it(repo, setting, tmp_path):
    marker = tmp_path / "ran"
    git(repo, "config", setting, f"touch {marker}")
    result = status(repo)
    assert not result["available"] and "could run commands" in result["error"] and not marker.exists()
    with pytest.raises(GitViewError, match="could run commands"):
        sides(repo, "main.c")
    assert not marker.exists()


def test_a_filter_in_the_attributes_cannot_run_a_program_because_its_settings_are_refused(repo, tmp_path):
    marker = tmp_path / "ran"
    (repo / ".gitattributes").write_text("*.c filter=evil\n")
    git(repo, "config", "filter.evil.clean", f"touch {marker}; cat")
    (repo / "main.c").write_text("changed\n")
    assert not status(repo)["available"] and not marker.exists()


@pytest.mark.parametrize("setting,value", [("user.name", "me"), ("core.autocrlf", "false"), ("pull.rebase", "false"), ("color.ui", "auto"), ("push.default", "simple")])
def test_harmless_settings_do_not_stop_it(repo, setting, value):
    git(repo, "config", setting, value)
    assert status(repo)["available"] is True


def test_the_hook_of_the_repository_is_never_run(repo, tmp_path):
    marker = tmp_path / "hook-ran"
    hook = repo / ".git" / "hooks" / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    (repo / "main.c").write_text("changed\n")
    status(repo)
    sides(repo, "main.c")
    assert not marker.exists()


def test_git_is_told_to_ignore_the_monitor_and_the_hooks_of_the_repository(repo, tmp_path):
    # (the settings are refused before this matters, so the switches are tried on their own)
    ran = tmp_path / "monitor-ran"
    monitor = repo / "monitor.sh"
    monitor.write_text(f"#!/bin/sh\ntouch {ran}\nprintf '\\0'\n")
    monitor.chmod(0o755)
    git(repo, "config", "core.fsmonitor", str(monitor))
    gitview._git(repo, "status")
    assert not ran.exists()
    hook_ran = tmp_path / "hook-ran"
    hook = repo / ".git" / "hooks" / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch {hook_ran}\n")
    hook.chmod(0o755)
    gitview._git(repo, "checkout", "main")
    assert not hook_ran.exists()


def test_a_config_git_cannot_read_is_not_taken_for_an_empty_one(repo):
    (repo / ".git" / "config").write_text("[core\n")
    result = status(repo)
    assert not result["available"] and "could not read" in result["error"]


def test_a_file_named_like_a_record_does_not_make_a_second_entry(repo):
    (repo / "? odd.c").write_text("int odd;\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "odd")
    (repo / "? odd.c").rename(repo / "odd.c")
    git(repo, "add", "-A")
    assert files(status(repo)) == {"odd.c": ("R", "", "renamed")}


def test_the_two_sides_of_a_change(repo):
    (repo / "main.c").write_text("int main(void)\n{\n\treturn (1);\n}\n")
    one = sides(repo, "main.c")
    assert one["before"].count("return (0)") == 1 and one["after"].count("return (1)") == 1 and one["state"] == "modified" and not one["binary"]
    (repo / "fresh.c").write_text("new\n")
    fresh = sides(repo, "fresh.c")
    assert fresh["before"] == "" and fresh["after"] == "new\n" and fresh["state"] == "added"
    (repo / "old.c").unlink()
    gone = sides(repo, "old.c")
    assert gone["before"] == "int old;\n" and gone["after"] == "" and gone["state"] == "deleted"
    git(repo, "add", "main.c")
    (repo / "main.c").write_text("later\n")
    staged = sides(repo, "main.c", staged=True)
    assert "return (0)" in staged["before"] and "return (1)" in staged["after"]            # the last commit against the index
    unstaged = sides(repo, "main.c")
    assert "return (1)" in unstaged["before"] and unstaged["after"] == "later\n"           # the index against the file now


def test_a_renamed_file_is_compared_with_where_it_was(repo):
    (repo / "dir" / "util.c").rename(repo / "dir" / "tools.c")
    (repo / "dir" / "tools.c").write_text("int tools;\n")
    git(repo, "add", "-A", "dir")
    renamed = sides(repo, "dir/tools.c", staged=True, old="dir/util.c")
    assert renamed["before"] == "int util;\n" and renamed["after"] == "int tools;\n" and renamed["state"] == "modified"
    with pytest.raises(GitViewError, match="not a path"):
        sides(repo, "dir/tools.c", staged=True, old="../x")


def test_a_file_emptied_and_staged_is_empty_not_the_old_one(repo):
    (repo / "old.c").write_text("")
    git(repo, "add", "old.c")
    (repo / "old.c").write_text("later\n")
    unstaged = sides(repo, "old.c")
    assert unstaged["before"] == "" and unstaged["after"] == "later\n"


def test_binary_files_are_not_sent_as_text(repo):
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02binary")
    git(repo, "add", "blob.bin")
    git(repo, "commit", "-qm", "bin")
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02changed")
    result = sides(repo, "blob.bin")
    assert result["binary"] and result["before"] == "" and result["after"] == ""


@pytest.mark.parametrize("path", ["", "-x", "../etc/passwd", "a/../../b", "x\0y", "/etc/passwd"])
def test_a_path_that_is_not_of_the_project_is_refused(repo, path):
    with pytest.raises(GitViewError, match="not a path"):
        sides(repo, path)


def test_a_link_is_shown_as_where_it_points_and_never_followed(repo, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    (repo / "link").symlink_to(secret)
    result = sides(repo, "link")
    assert "top secret" not in result["after"] and result["after"] == str(secret) and result["state"] == "added"


def test_a_folder_that_leads_out_of_the_project_is_not_entered(repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.txt").write_text("top secret")
    (repo / "evil").symlink_to(outside)
    with pytest.raises(GitViewError, match="cannot be read"):
        sides(repo, "evil/x.txt")


def test_a_pipe_left_in_the_folder_is_not_waited_for(repo):
    os.mkfifo(repo / "pipe")
    assert sides(repo, "pipe")["after"] == ""


def test_big_files_are_cut(repo, monkeypatch):
    monkeypatch.setattr(gitview, "MAX_BYTES", 50)
    (repo / "big.txt").write_text("x" * 500)
    result = sides(repo, "big.txt")
    assert result["truncated"] and len(result["after"]) == 50


# ---------------------------------------------------------------- the endpoints


def test_the_endpoints_read_the_project_of_the_session(client, repo, tmp_path):
    c, main = client
    sid = c.post("/api/sessions").json()["id"]
    assert c.get(f"/api/sessions/{sid}/git/status").status_code == 404
    target = attach_repo(main, sid, "gv1")
    for item in repo.iterdir():
        shutil.move(str(item), str(target / item.name))
    (target / "main.c").write_text("changed\n")
    answer = c.get(f"/api/sessions/{sid}/git/status").json()
    assert answer["available"] and files(answer) == {"main.c": ("", "M", "modified")}
    diff = c.get(f"/api/sessions/{sid}/git/diff", params={"path": "main.c"}).json()
    assert diff["after"] == "changed\n" and "return (0)" in diff["before"]
    assert c.get(f"/api/sessions/{sid}/git/diff", params={"path": "../x"}).status_code == 400
    assert c.get("/api/sessions/nope/git/status").status_code == 404
