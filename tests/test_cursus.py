"""scripts/cursus.sh update: scratch repositories on disk stand in for GitHub; nothing here touches the real 42Cursus."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "cursus.sh"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

ENV = {**os.environ, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow", "GIT_CONFIG_VALUE_0": "always",     # (file:// remotes)
       "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "GIT_TERMINAL_PROMPT": "0"}
ENV.pop("CURSUS_PUSH", None)


def git(*args, cwd):
    done = subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout.strip()


class World:
    """Projects with a 'GitHub' each, and a 42Cursus that has them as submodules (with a 'GitHub' of its own)."""

    def __init__(self, base: Path):
        self.base = base
        (base / "remotes").mkdir()
        (base / "work").mkdir()
        self.cursus = base / "42Cursus"

    def project(self, name: str) -> str:
        """A project repository: its bare 'GitHub', and a working clone to make new commits in."""
        bare, work = self.base / "remotes" / f"{name}.git", self.base / "work" / name
        git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.base)
        git("init", "-q", "-b", "main", str(work), cwd=self.base)
        git("remote", "add", "origin", str(bare), cwd=work)
        return self.commit(name, "first")

    def commit(self, name: str, message: str) -> str:
        work = self.base / "work" / name
        (work / f"{message}.txt").write_text(message)
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", message, cwd=work)
        git("push", "-q", "-u", "origin", "main", cwd=work)
        return git("rev-parse", "HEAD", cwd=work)

    def build(self, *paths: str):
        """42Cursus with one submodule per `track/name` path, committed and pushed to its own bare repository."""
        git("init", "-q", "-b", "main", str(self.cursus), cwd=self.base)
        for path in paths:
            git("submodule", "add", "-q", str(self.base / "remotes" / f"{Path(path).name}.git"), path, cwd=self.cursus)
        git("commit", "-q", "-m", "Add projects", cwd=self.cursus)
        bare = self.base / "remotes" / "42Cursus.git"
        git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.base)
        git("remote", "add", "origin", str(bare), cwd=self.cursus)
        git("push", "-q", "-u", "origin", "main", cwd=self.cursus)

    def position(self, path: str, repo: Path | None = None) -> str:
        return git("rev-parse", f"HEAD:{path}", cwd=repo or self.cursus)

    def commits(self, repo: Path | None = None) -> int:
        return int(git("rev-list", "--count", "HEAD", cwd=repo or self.cursus))

    def update(self, repo: Path | None = None, **env):
        done = subprocess.run(["sh", str(SCRIPT), "update"], env={**ENV, "CURSUS_DIR": str(repo or self.cursus), **env}, capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_a_project_with_new_commits_is_moved_and_committed_and_the_others_are_left_alone(world):
    libft, nm = world.project("libft"), world.project("nm")
    world.build("common-core/libft", "rncp/nm")
    newest = world.commit("libft", "second")
    before = world.commits()
    code, out = world.update()
    assert code == 0, out
    assert f"up   common-core/libft: {libft[:7]} -> {newest[:7]} (1 new commit(s))" in out and "ok   rncp/nm: already the newest" in out
    assert world.position("common-core/libft") == newest and world.position("rncp/nm") == nm
    assert world.commits() == before + 1 and git("log", "-1", "--format=%s", cwd=world.cursus) == "Update 1 project(s)"
    assert git("rev-parse", "HEAD", cwd=world.cursus / "common-core" / "libft") == newest                    # and the folder is really there
    assert git("status", "--porcelain", cwd=world.cursus) == ""
    assert "push with: git -C" in out


def test_everything_up_to_date_changes_nothing(world):
    world.project("libft")
    world.build("common-core/libft")
    before = world.commits()
    code, out = world.update()
    assert code == 0 and "nothing to update" in out and world.commits() == before


def test_several_projects_one_commit_and_a_folder_name_with_a_space_works(world):
    world.project("libft"), world.project("my proj")
    world.build("common-core/libft", "common-core/my proj")
    a, b = world.commit("libft", "second"), world.commit("my proj", "second")
    before = world.commits()
    code, out = world.update()
    assert code == 0, out
    assert world.position("common-core/libft") == a and world.position("common-core/my proj") == b
    assert world.commits() == before + 1 and "Update 2 project(s)" in git("log", "-1", "--format=%s", cwd=world.cursus)
    assert "common-core/libft" in git("log", "-1", "--format=%b", cwd=world.cursus) and "common-core/my proj" in git("log", "-1", "--format=%b", cwd=world.cursus)


def test_a_project_with_uncommitted_changes_is_skipped_and_the_rest_still_updates(world):
    world.project("libft"), world.project("nm")
    world.build("common-core/libft", "rncp/nm")
    pinned = world.position("common-core/libft")
    world.commit("libft", "second")
    nm_new = world.commit("nm", "second")
    (world.cursus / "common-core" / "libft" / "my-work.c").write_text("work in progress\n")
    git("add", "my-work.c", cwd=world.cursus / "common-core" / "libft")
    code, out = world.update()
    assert code == 0 and "skip common-core/libft: it has uncommitted changes" in out and "1 project(s) skipped" in out
    assert world.position("common-core/libft") == pinned and world.position("rncp/nm") == nm_new
    assert (world.cursus / "common-core" / "libft" / "my-work.c").read_text() == "work in progress\n"       # untouched


def test_commits_that_are_only_on_your_machine_are_never_overwritten(world):
    world.project("libft")
    world.build("common-core/libft")
    checkout = world.cursus / "common-core" / "libft"
    (checkout / "mine.txt").write_text("a commit I have not pushed\n")
    git("add", "mine.txt", cwd=checkout)
    git("commit", "-q", "-m", "local only", cwd=checkout)
    mine = git("rev-parse", "HEAD", cwd=checkout)
    world.commit("libft", "second")
    code, out = world.update()
    assert code == 0 and "skip common-core/libft: it has commits that are not on its origin (push them first)" in out
    assert git("rev-parse", "HEAD", cwd=checkout) == mine and (checkout / "mine.txt").exists()               # still checked out, still there


def test_a_fresh_clone_without_its_projects_checked_out_gets_them_and_the_newest_commits(world):
    world.project("libft")
    world.build("common-core/libft")
    fresh = world.base / "fresh"
    git("clone", "-q", str(world.base / "remotes" / "42Cursus.git"), str(fresh), cwd=world.base)       # no --recurse-submodules
    assert not (fresh / "common-core" / "libft" / ".git").exists()
    newest = world.commit("libft", "second")
    code, out = world.update(fresh)
    assert code == 0, out
    assert git("rev-parse", "HEAD", cwd=fresh / "common-core" / "libft") == newest and world.position("common-core/libft", fresh) == newest


def test_a_project_that_cannot_be_fetched_is_reported_and_does_not_stop_the_others(world):
    world.project("libft"), world.project("nm")
    world.build("common-core/libft", "rncp/nm")
    world.commit("libft", "second")
    nm_new = world.commit("nm", "second")
    shutil.rmtree(world.base / "remotes" / "libft.git")                                                       # its 'GitHub' is gone
    code, out = world.update()
    assert code == 1 and "fail common-core/libft: could not fetch from its origin" in out and "1 project(s) could not be updated" in out
    assert world.position("rncp/nm") == nm_new                                                                  # the other one was still done


def test_only_the_updated_projects_are_committed_never_something_else_that_was_staged(world):
    world.project("libft")
    world.build("common-core/libft")
    (world.cursus / "notes.md").write_text("my notes\n")
    git("add", "notes.md", cwd=world.cursus)
    world.commit("libft", "second")
    code, out = world.update()
    assert code == 0, out
    assert git("show", "--name-only", "--format=", "HEAD", cwd=world.cursus) == "common-core/libft"
    assert git("status", "--porcelain", cwd=world.cursus) == "A  notes.md"                                    # still staged, not committed


def test_nothing_is_pushed_unless_asked_and_then_it_is(world):
    world.project("libft")
    world.build("common-core/libft")
    bare = world.base / "remotes" / "42Cursus.git"
    newest = world.commit("libft", "second")
    code, out = world.update()
    assert code == 0 and world.position("common-core/libft", bare) != newest                                  # committed here, not on 'GitHub'
    newest = world.commit("libft", "third")
    code, out = world.update(CURSUS_PUSH="1")
    assert code == 0 and "cursus: pushed" in out and world.position("common-core/libft", bare) == newest


def test_positions_recorded_on_another_machine_are_picked_up_first(world):
    world.project("libft")
    world.build("common-core/libft")
    other = world.base / "other"
    git("clone", "-q", "--recurse-submodules", str(world.base / "remotes" / "42Cursus.git"), str(other), cwd=world.base)
    newest = world.commit("libft", "second")
    code, out = world.update(other, CURSUS_PUSH="1")                                                          # the other machine updates and pushes
    assert code == 0 and world.position("common-core/libft", other) == newest
    before = world.commits()
    code, out = world.update()                                                                                # this one fast-forwards to it first
    assert code == 0 and world.position("common-core/libft") == newest and "nothing to update" in out
    assert world.commits() == before + 1                                                                      # (the other machine's commit, not a new one)


def test_it_explains_when_there_is_no_repository_or_no_project_yet(world, tmp_path):
    code, out = world.update(tmp_path / "does-not-exist")
    assert code == 1 and "does not exist yet: run init first" in out
    empty = tmp_path / "empty"
    git("init", "-q", "-b", "main", str(empty), cwd=tmp_path)
    code, out = world.update(empty)
    assert code == 0 and "no projects in" in out and "run sort first" in out


def test_the_make_target_and_the_usage_line_exist():
    makefile = (ROOT / "Makefile").read_text()
    assert "cursus-update:\n\t@sh scripts/cursus.sh update\n" in makefile and "cursus-update" in makefile.split(".PHONY:")[1]
    done = subprocess.run(["sh", str(SCRIPT), "nonsense"], capture_output=True, text=True)
    assert done.returncode == 2 and "| update" in done.stderr
