"""scripts/cursus.sh: bare repositories on disk stand in for GitHub; nothing here touches the real 42Cursus or the real projects."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "cursus.sh"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

ENV = {**os.environ, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow", "GIT_CONFIG_VALUE_0": "always",     # (file:// remotes)
       "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "GIT_TERMINAL_PROMPT": "0"}
for name in ("CURSUS_PUSH", "CURSUS_DIR", "CURSUS_URL", "CURSUS_REPO", "CURSUS_DRY_RUN", "CURSUS_VISIBILITY", "PROJECTS_DIR", "GIT_ALLOW_PROTOCOL"):
    ENV.pop(name, None)


def git(*args, cwd):
    done = subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout.strip()


class World:
    """Projects with a 'GitHub' each (a bare repository), a projects folder with a clone of some of them, and a 42Cursus 'GitHub'."""

    def __init__(self, base: Path):
        self.base = base
        for d in ("remotes", "work", "projects", "tmp"):
            (base / d).mkdir()
        self.cursus = base / "remotes" / "42Cursus.git"          # the 'GitHub' of 42Cursus
        self.projects = base / "projects"

    def remote(self, name: str) -> Path:
        return self.base / "remotes" / f"{name}.git"

    def project(self, name: str) -> str:
        """A project repository: its bare 'GitHub', and a working clone (in `work`) to make new commits in."""
        work = self.base / "work" / name
        git("init", "-q", "--bare", "-b", "main", str(self.remote(name)), cwd=self.base)
        git("init", "-q", "-b", "main", str(work), cwd=self.base)
        git("remote", "add", "origin", str(self.remote(name)), cwd=work)
        return self.commit(name, "first")

    def commit(self, name: str, message: str, where: Path | None = None) -> str:
        """A commit pushed to the project's 'GitHub' from its working clone (or from `where`)."""
        work = where or self.base / "work" / name
        (work / f"{message}.txt").write_text(message)
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", message, cwd=work)
        git("push", "-q", "-u", "origin", "main", cwd=work)
        return git("rev-parse", "HEAD", cwd=work)

    def local(self, name: str) -> Path:
        """The project in the projects folder: a clone of its 'GitHub', like the ones this app makes."""
        git("clone", "-q", str(self.remote(name)), str(self.projects / name), cwd=self.base)
        return self.projects / name

    def build(self, *paths: str):
        """42Cursus with one submodule per `track/name` path, pushed to its 'GitHub'."""
        work = self.base / "work" / "42Cursus"
        git("init", "-q", "--bare", "-b", "main", str(self.cursus), cwd=self.base)
        git("init", "-q", "-b", "main", str(work), cwd=self.base)
        for path in paths:
            git("submodule", "add", "-q", str(self.remote(Path(path).name)), path, cwd=work)
        git("commit", "-q", "-m", "Add projects", "--allow-empty", cwd=work)
        git("remote", "add", "origin", str(self.cursus), cwd=work)
        git("push", "-q", "-u", "origin", "main", cwd=work)

    def position(self, path: str) -> str:
        return git("rev-parse", f"HEAD:{path}", cwd=self.cursus)

    def commits(self) -> int:
        return int(git("rev-list", "--count", "HEAD", cwd=self.cursus))

    def run(self, *args, **env):
        done = subprocess.run(["sh", str(SCRIPT), *args], capture_output=True, text=True, timeout=120,
                              env={**ENV, "CURSUS_URL": str(self.cursus), "PROJECTS_DIR": str(self.projects), "TMPDIR": str(self.base / "tmp"), **env})
        return done.returncode, done.stdout + done.stderr

    def update(self, **env):
        return self.run("update", **env)

    def leftovers(self):
        """Temporary folders the script forgot to delete."""
        return sorted(p.name for p in (self.base / "tmp").iterdir())


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


# ---------------------------------------------------------------- update


def test_a_project_with_new_commits_is_moved_committed_and_pushed_and_the_others_are_left_alone(world):
    libft, nm = world.project("libft"), world.project("nm")
    world.build("common-core/libft", "rncp/nm")
    newest = world.commit("libft", "second")
    before = world.commits()
    code, out = world.update()
    assert code == 0, out
    assert f"up   common-core/libft: {libft[:7]} -> {newest[:7]}" in out and "ok   rncp/nm: already the newest" in out
    assert world.position("common-core/libft") == newest and world.position("rncp/nm") == nm                  # (on 'GitHub' itself)
    assert world.commits() == before + 1 and git("log", "-1", "--format=%s", cwd=world.cursus) == "Update 1 project(s)"
    assert "pushed to Rodolfo9898/42Cursus (1 project(s) updated)" in out
    assert world.leftovers() == []                                                                              # the temporary clone is gone


def test_nothing_is_kept_on_this_machine_so_no_local_copy_of_42cursus_is_needed(world):
    world.project("libft")
    world.build("common-core/libft")
    newest = world.commit("libft", "second")
    assert not (world.base.parent / "42Cursus").exists()
    code, out = world.update(CURSUS_DIR=str(world.base / "does-not-exist"))                                      # (the old setting is ignored)
    assert code == 0 and world.position("common-core/libft") == newest
    assert sorted(p.name for p in world.base.iterdir()) == ["projects", "remotes", "tmp", "work"]              # (no folder was made for it)


def test_everything_up_to_date_changes_and_pushes_nothing(world):
    world.project("libft")
    world.build("common-core/libft")
    before = world.commits()
    code, out = world.update()
    assert code == 0 and "nothing to update" in out and world.commits() == before and "pushed" not in out


def test_several_projects_one_commit_and_a_folder_name_with_a_space_works(world):
    world.project("libft"), world.project("my proj")
    world.build("common-core/libft", "common-core/my proj")
    a, b = world.commit("libft", "second"), world.commit("my proj", "second")
    before = world.commits()
    code, out = world.update()
    assert code == 0, out
    assert world.position("common-core/libft") == a and world.position("common-core/my proj") == b
    body = git("log", "-1", "--format=%b", cwd=world.cursus)
    assert world.commits() == before + 1 and "Update 2 project(s)" in git("log", "-1", "--format=%s", cwd=world.cursus)
    assert body.splitlines() == ["common-core/libft", "common-core/my proj"]


def test_a_project_that_cannot_be_read_is_reported_and_does_not_stop_the_others(world):
    world.project("libft"), world.project("nm")
    world.build("common-core/libft", "rncp/nm")
    world.commit("libft", "second")
    nm_new = world.commit("nm", "second")
    shutil.rmtree(world.remote("libft"))                                                                        # its 'GitHub' is gone
    code, out = world.update()
    assert code == 1 and "fail common-core/libft: could not read the newest commit of its origin" in out and "1 project(s) could not be updated" in out
    assert world.position("rncp/nm") == nm_new                                                                  # the other one was still done and pushed


def test_a_dry_run_does_everything_but_push(world):
    world.project("libft")
    world.build("common-core/libft")
    before = world.position("common-core/libft")
    world.commit("libft", "second")
    code, out = world.update(CURSUS_DRY_RUN="1")
    assert code == 0 and "up   common-core/libft" in out and "dry run, nothing pushed" in out
    assert world.position("common-core/libft") == before and world.leftovers() == []


def test_a_branch_named_in_gitmodules_is_followed_instead_of_the_default_one(world):
    world.project("libft")
    world.build("common-core/libft")
    work = world.base / "work" / "libft"
    git("checkout", "-q", "-b", "dev", cwd=work)
    (work / "dev.txt").write_text("dev")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "dev work", cwd=work)
    git("push", "-q", "origin", "dev", cwd=work)
    on_dev = git("rev-parse", "HEAD", cwd=work)
    editor = world.base / "work" / "42Cursus"
    git("config", "-f", ".gitmodules", "submodule.common-core/libft.branch", "dev", cwd=editor)
    git("commit", "-q", "-am", "follow dev", cwd=editor)
    git("push", "-q", cwd=editor)
    code, out = world.update()
    assert code == 0 and world.position("common-core/libft") == on_dev, out


def test_a_push_that_is_refused_is_an_error_and_says_so(world):
    world.project("libft")
    world.build("common-core/libft")
    world.commit("libft", "second")
    hook = world.cursus / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'no pushes today' >&2\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    code, out = world.update()
    assert code == 1 and "could not push to Rodolfo9898/42Cursus" in out and world.leftovers() == []


def test_a_gitlink_without_its_gitmodules_entry_is_skipped_not_guessed(world):
    world.project("libft")
    world.build("common-core/libft")
    editor = world.base / "work" / "42Cursus"
    git("rm", "-q", "-f", ".gitmodules", cwd=editor)                                  # the commit stays a gitlink, but nothing says where it lives
    git("commit", "-q", "-m", "oops", cwd=editor)
    git("push", "-q", cwd=editor)
    code, out = world.update()
    assert code == 0 and "skip common-core/libft: .gitmodules has no URL for it" in out and "1 project(s) skipped" in out


def test_an_address_that_would_run_a_command_or_is_an_option_is_never_followed(world, tmp_path):
    world.project("libft")
    marker = tmp_path / "ran"
    world.build("common-core/libft")
    editor = world.base / "work" / "42Cursus"
    for url in (f"ext::sh -c 'touch {marker}'", f"--upload-pack=touch {marker}"):
        git("config", "-f", ".gitmodules", "submodule.common-core/libft.url", url, cwd=editor)
        git("commit", "-q", "-am", "evil", cwd=editor)
        git("push", "-q", cwd=editor)
        code, out = world.update()
        assert code == 1 and "fail common-core/libft" in out and not marker.exists(), url


def test_it_explains_when_there_is_no_repository_no_commit_or_no_project_yet(world):
    code, out = world.update()
    assert code == 1 and f"cannot reach {world.cursus}" in out and "make cursus" in out
    git("init", "-q", "--bare", "-b", "main", str(world.cursus), cwd=world.base)
    code, out = world.update()
    assert code == 1 and "has no commits yet: run: make cursus" in out
    work = world.base / "work" / "empty"
    git("init", "-q", "-b", "main", str(work), cwd=world.base)
    git("commit", "-q", "--allow-empty", "-m", "Initial commit", cwd=work)
    git("push", "-q", str(world.cursus), "main", cwd=work)
    code, out = world.update()
    assert code == 0 and "no projects in" in out and "make cursus-sort" in out and world.leftovers() == []


# ---------------------------------------------------------------- sort


def test_sorting_adds_each_project_at_the_commit_github_has_and_pushes_it(world):
    libft, nm = world.project("libft"), world.project("nm")
    world.local("libft"), world.local("nm")
    (world.projects / "notes").mkdir()                                                    # not a git repository
    git("init", "-q", "-b", "main", str(world.projects / "bare-start"), cwd=world.base)  # a git repository with no origin
    world.build()
    code, out = world.run("sort", "libft=common-core", "nm=rncp")
    assert code == 0, out
    assert f"add  libft -> common-core/ ({libft[:7]})" in out and f"add  nm -> rncp/ ({nm[:7]})" in out
    assert "skip notes: not a git repository" in out and "skip bare-start: no origin remote" in out
    assert world.position("common-core/libft") == libft and world.position("rncp/nm") == nm
    assert git("ls-tree", "HEAD", "common-core/libft", cwd=world.cursus).startswith("160000 commit")           # a real gitlink
    assert git("log", "-1", "--format=%s", cwd=world.cursus) == "Add 2 project(s)" and "pushed to" in out and world.leftovers() == []
    fresh = world.base / "fresh"
    git("clone", "-q", "--recurse-submodules", str(world.cursus), str(fresh), cwd=world.base)                    # and git can really use it
    assert git("rev-parse", "HEAD", cwd=fresh / "common-core" / "libft") == libft and (fresh / "rncp" / "nm" / "first.txt").exists()


def test_sorting_twice_adds_nothing_the_second_time(world):
    world.project("libft")
    world.local("libft")
    world.build()
    world.run("sort", "libft=common-core")
    before = world.commits()
    code, out = world.run("sort", "libft=common-core")
    assert code == 0 and "ok   libft: already in common-core/" in out and "nothing to add" in out and world.commits() == before


def test_unpushed_work_is_warned_about_and_the_commit_recorded_is_the_one_github_has(world):
    on_github = world.project("libft")
    local = world.local("libft")
    (local / "mine.txt").write_text("not pushed")
    git("add", "-A", cwd=local)
    git("commit", "-q", "-m", "local only", cwd=local)
    (local / "dirty.txt").write_text("not even committed")
    world.build()
    code, out = world.run("sort", "libft=common-core")
    assert code == 0 and "warn libft: unpushed commits or uncommitted changes" in out and "make cursus-push" in out
    assert world.position("common-core/libft") == on_github


def test_a_project_whose_github_cannot_be_read_is_reported_and_the_others_are_still_added(world):
    world.project("libft"), world.project("nm")
    world.local("libft")
    nm = world.local("nm")
    world.build()
    git("remote", "set-url", "origin", str(world.base / "remotes" / "gone.git"), cwd=world.projects / "libft")
    code, out = world.run("sort", "libft=common-core", "nm=rncp")
    assert code == 1 and "fail libft: could not read" in out and "1 project(s) could not be added" in out
    assert git("ls-tree", "--name-only", "HEAD", "rncp/nm", cwd=world.cursus) == "rncp/nm" and git("ls-tree", "--name-only", "HEAD", "common-core/libft", cwd=world.cursus) == ""


def test_a_project_with_no_subject_pdf_of_its_name_needs_a_track_and_a_wrong_one_is_refused(world):
    world.project("zzz_not_a_subject")
    world.local("zzz_not_a_subject")
    world.build()
    code, out = world.run("sort")
    assert code == 0 and "skip zzz_not_a_subject: no subject PDF with this name; run again with zzz_not_a_subject=<track>" in out and "nothing to add" in out
    code, out = world.run("sort", "zzz_not_a_subject=nowhere")
    assert code == 1 and "unknown track 'nowhere'" in out
    code, out = world.run("sort", "libft")
    assert code == 1 and "expected name=track" in out


def test_a_folder_of_repositories_is_kept_as_a_folder_under_the_track_of_its_projects(world):
    cpp00, utils = world.project("cpp00"), world.project("cpp_utils")
    group = world.projects / "cpp-modules"
    group.mkdir()
    for name in ("cpp00", "cpp_utils"):
        git("clone", "-q", str(world.remote(name)), str(group / name), cwd=world.base)
    (group / "notes").mkdir()                                                             # not a repository: ignored
    (world.projects / "empty").mkdir()
    world.build()
    code, out = world.run("sort")
    assert code == 0, out
    assert f"add  cpp-modules/cpp00 -> common-core/cpp-modules/ ({cpp00[:7]})" in out          # cpp00.pdf is in common-core
    assert f"add  cpp-modules/cpp_utils -> common-core/cpp-modules/ ({utils[:7]})" in out      # and the whole group follows it
    assert "skip empty: not a git repository" in out and "notes" not in out
    assert world.position("common-core/cpp-modules/cpp00") == cpp00 and world.position("common-core/cpp-modules/cpp_utils") == utils
    code, out = world.run("sort")
    assert code == 0 and "ok   cpp-modules/cpp00: already in common-core/cpp-modules/" in out and "nothing to add" in out
    code, out = world.update()
    assert code == 0 and "ok   common-core/cpp-modules/cpp_utils: already the newest" in out


def test_a_group_with_no_subject_pdf_needs_a_track(world):
    world.project("zzz_a"), world.project("zzz_b")
    group = world.projects / "zzz-group"
    group.mkdir()
    for name in ("zzz_a", "zzz_b"):
        git("clone", "-q", str(world.remote(name)), str(group / name), cwd=world.base)
    world.build()
    code, out = world.run("sort")
    assert code == 0 and "skip zzz-group/: none of its projects has a subject PDF; run again with zzz-group=<track>" in out
    code, out = world.run("sort", "zzz-group=rncp")
    assert code == 0 and "add  zzz-group/zzz_a -> rncp/zzz-group/" in out and "add  zzz-group/zzz_b -> rncp/zzz-group/" in out


def test_a_dry_run_of_sort_pushes_nothing(world):
    world.project("libft")
    world.local("libft")
    world.build()
    before = world.commits()
    code, out = world.run("sort", "libft=common-core", CURSUS_DRY_RUN="1")
    assert code == 0 and "add  libft" in out and "dry run, nothing pushed" in out and world.commits() == before


# ---------------------------------------------------------------- push


def test_pushing_sends_the_new_commits_of_every_project_and_says_what_to_do_next(world):
    world.project("libft"), world.project("nm")
    libft, nm = world.local("libft"), world.local("nm")
    for repo, text in ((libft, "a"), (libft, "b")):
        (repo / f"{text}.txt").write_text(text)
        git("add", "-A", cwd=repo)
        git("commit", "-q", "-m", text, cwd=repo)
    (nm / "wip.txt").write_text("not committed")
    code, out = world.run("push")
    assert code == 0, out
    assert "push libft: 2 commit(s) of main" in out and "ok   nm: nothing to push (uncommitted changes are not pushed)" in out
    assert git("rev-parse", "main", cwd=world.remote("libft")) == git("rev-parse", "HEAD", cwd=libft)
    assert "pushed 1 project(s); run: make cursus-update" in out
    code, out = world.run("push")
    assert code == 0 and "ok   libft: nothing to push" in out and "pushed 0" not in out and "make cursus-update" not in out


def test_only_the_named_projects_are_pushed_and_a_bad_name_is_refused(world):
    world.project("libft"), world.project("nm")
    libft, nm = world.local("libft"), world.local("nm")
    for repo in (libft, nm):
        (repo / "x.txt").write_text("x")
        git("add", "-A", cwd=repo)
        git("commit", "-q", "-m", "x", cwd=repo)
    code, out = world.run("push", "nm")
    assert code == 0 and "push nm" in out and "libft" not in out
    assert git("rev-parse", "main", cwd=world.remote("libft")) != git("rev-parse", "HEAD", cwd=libft)
    for bad in ("../libft", "a/b/c", "a/..", ".hidden", "/abs", "a/", ""):
        code, out = world.run("push", bad)
        assert code == 1 and "is not a project name" in out, bad
    code, out = world.run("push", "missing")
    assert code == 1 and "no project 'missing'" in out


def test_a_push_is_never_forced_and_a_failure_does_not_stop_the_others(world):
    world.project("libft"), world.project("nm")
    libft, nm = world.local("libft"), world.local("nm")
    world.commit("libft", "elsewhere")                                                    # GitHub moved on without this clone
    for repo in (libft, nm):
        (repo / "mine.txt").write_text("mine")
        git("add", "-A", cwd=repo)
        git("commit", "-q", "-m", "mine", cwd=repo)
    on_github = git("rev-parse", "main", cwd=world.remote("libft"))
    code, out = world.run("push")
    assert code == 1 and "fail libft: not pushed" in out and "never forced" in out and "push nm: 1 commit(s)" in out
    assert git("rev-parse", "main", cwd=world.remote("libft")) == on_github                  # untouched


def test_a_new_branch_is_pushed_with_its_upstream_and_a_detached_head_or_no_origin_is_skipped(world):
    world.project("libft"), world.project("nm")
    libft, nm = world.local("libft"), world.local("nm")
    git("checkout", "-q", "-b", "feature", cwd=libft)
    (libft / "f.txt").write_text("f")
    git("add", "-A", cwd=libft)
    git("commit", "-q", "-m", "f", cwd=libft)
    git("checkout", "-q", "--detach", cwd=nm)
    git("init", "-q", "-b", "main", str(world.projects / "alone"), cwd=world.base)
    code, out = world.run("push")
    assert code == 0, out
    assert "push libft: 1 commit(s) of feature" in out and "skip nm: not on a branch" in out and "skip alone: no origin remote" in out
    assert git("rev-parse", "feature", cwd=world.remote("libft")) == git("rev-parse", "HEAD", cwd=libft)
    assert git("rev-parse", "--abbrev-ref", "@{u}", cwd=libft) == "origin/feature"


def test_the_repositories_of_a_group_are_pushed_all_together_or_one_by_one(world):
    world.project("cpp00"), world.project("cpp01")
    group = world.projects / "cpp-modules"
    group.mkdir()
    for name in ("cpp00", "cpp01"):
        repo = group / name
        git("clone", "-q", str(world.remote(name)), str(repo), cwd=world.base)
        (repo / "x.txt").write_text("x")
        git("add", "-A", cwd=repo)
        git("commit", "-q", "-m", "x", cwd=repo)
    code, out = world.run("push", "cpp-modules/cpp01")
    assert code == 0 and "push cpp-modules/cpp01: 1 commit(s) of main" in out and "cpp00" not in out
    code, out = world.run("push")
    assert code == 0 and "push cpp-modules/cpp00: 1 commit(s) of main" in out and "ok   cpp-modules/cpp01: nothing to push" in out
    assert git("rev-parse", "main", cwd=world.remote("cpp00")) == git("rev-parse", "HEAD", cwd=group / "cpp00")
    code, out = world.run("push", "cpp-modules")
    assert code == 0 and "ok   cpp-modules/cpp00" in out and "ok   cpp-modules/cpp01" in out


def test_a_dry_run_of_push_pushes_nothing(world):
    world.project("libft")
    libft = world.local("libft")
    (libft / "x.txt").write_text("x")
    git("add", "-A", cwd=libft)
    git("commit", "-q", "-m", "x", cwd=libft)
    on_github = git("rev-parse", "main", cwd=world.remote("libft"))
    code, out = world.run("push", CURSUS_DRY_RUN="1")
    assert code == 0 and "dry  libft: would push 1 commit(s) of main" in out and git("rev-parse", "main", cwd=world.remote("libft")) == on_github


# ---------------------------------------------------------------- refresh


def test_refreshing_pulls_the_new_commits_of_every_project_and_leaves_your_uncommitted_work_alone(world):
    world.project("libft"), world.project("nm")
    libft, nm = world.local("libft"), world.local("nm")
    (nm / "wip.txt").write_text("not committed")
    world.commit("libft", "two"), world.commit("libft", "three")
    newest = world.commit("nm", "two")
    code, out = world.run("refresh")
    assert code == 0, out
    assert "pull libft: 2 commit(s) of main" in out and "pull nm: 1 commit(s) of main (uncommitted changes stay as they are)" in out
    assert "cursus: pulled 2 project(s)" in out
    assert git("rev-parse", "HEAD", cwd=nm) == newest and (nm / "two.txt").exists() and (nm / "wip.txt").read_text() == "not committed"
    assert git("rev-parse", "HEAD", cwd=libft) == git("rev-parse", "main", cwd=world.remote("libft"))
    code, out = world.run("refresh")
    assert code == 0 and "ok   libft: already up to date" in out and "pulled" not in out
    assert git("log", "--merges", "--oneline", cwd=libft) == "", "a pull is a fast-forward, never a merge commit"


def test_only_the_named_projects_are_refreshed_and_a_bad_name_is_refused(world):
    world.project("libft"), world.project("nm")
    libft, nm = world.local("libft"), world.local("nm")
    world.commit("libft", "two"), world.commit("nm", "two")
    before = git("rev-parse", "HEAD", cwd=libft)
    code, out = world.run("refresh", "nm")
    assert code == 0 and "pull nm" in out and "libft" not in out and git("rev-parse", "HEAD", cwd=libft) == before
    for bad in ("../libft", "a/b/c", ".hidden", "/abs", ""):
        code, out = world.run("refresh", bad)
        assert code == 1 and "is not a project name" in out, bad
    code, out = world.run("refresh", "missing")
    assert code == 1 and "no project 'missing'" in out


def test_the_repositories_of_a_group_are_refreshed_with_it_or_one_by_one(world):
    world.project("cpp00"), world.project("cpp01")
    group = world.projects / "cpp-modules"
    group.mkdir()
    for name in ("cpp00", "cpp01"):
        git("clone", "-q", str(world.remote(name)), str(group / name), cwd=world.base)
        world.commit(name, "two")
    code, out = world.run("refresh", "cpp-modules/cpp01")
    assert code == 0 and "pull cpp-modules/cpp01: 1 commit(s)" in out and "cpp00" not in out
    code, out = world.run("refresh", "cpp-modules")
    assert code == 0 and "pull cpp-modules/cpp00: 1 commit(s)" in out and "ok   cpp-modules/cpp01: already up to date" in out
    for name in ("cpp00", "cpp01"):
        assert git("rev-parse", "HEAD", cwd=group / name) == git("rev-parse", "main", cwd=world.remote(name))


def test_a_branch_that_has_diverged_or_is_in_the_way_of_your_changes_is_reported_and_nothing_is_changed(world):
    world.project("libft"), world.project("nm"), world.project("push_swap")
    libft, nm, ps = world.local("libft"), world.local("nm"), world.local("push_swap")
    (libft / "mine.txt").write_text("mine")                                                # a commit GitHub does not have
    git("add", "-A", cwd=libft)
    git("commit", "-q", "-m", "mine", cwd=libft)
    world.commit("libft", "theirs")
    (nm / "two.txt").write_text("my own two")                                              # uncommitted, and the new commit adds the same file
    world.commit("nm", "two")
    world.commit("push_swap", "two")
    mine, edited = git("rev-parse", "HEAD", cwd=libft), git("rev-parse", "HEAD", cwd=nm)
    code, out = world.run("refresh")
    assert code == 1, out
    assert "fail libft: main has diverged (1 commit(s) here, 1 new on GitHub)" in out and "fail nm: not pulled" in out and "nothing was changed" in out
    assert "pull push_swap: 1 commit(s)" in out and "2 project(s) could not be refreshed" in out, "the others are still pulled"
    assert git("rev-parse", "HEAD", cwd=libft) == mine and git("rev-parse", "HEAD", cwd=nm) == edited
    assert (nm / "two.txt").read_text() == "my own two"


def test_work_not_pushed_yet_is_mentioned_and_a_detached_head_or_no_upstream_or_no_origin_is_skipped(world):
    world.project("libft"), world.project("nm"), world.project("push_swap")
    libft, nm, ps = world.local("libft"), world.local("nm"), world.local("push_swap")
    (libft / "x.txt").write_text("x")
    git("add", "-A", cwd=libft)
    git("commit", "-q", "-m", "x", cwd=libft)
    git("checkout", "-q", "--detach", cwd=nm)
    git("checkout", "-q", "-b", "feature", cwd=ps)
    git("init", "-q", "-b", "main", str(world.projects / "alone"), cwd=world.base)
    code, out = world.run("refresh")
    assert code == 0, out
    assert "ok   libft: up to date, with 1 commit(s) not pushed yet" in out and "skip nm: not on a branch" in out
    assert "skip push_swap: feature has no upstream branch" in out and "skip alone: no origin remote" in out


def test_a_project_that_cannot_be_fetched_is_reported_and_does_not_stop_the_others(world):
    world.project("libft"), world.project("nm")
    world.local("libft"), world.local("nm")
    world.commit("nm", "two")
    shutil.rmtree(world.remote("libft"))                                                   # its GitHub is gone
    code, out = world.run("refresh")
    assert code == 1 and "fail libft: could not fetch" in out and "pull nm: 1 commit(s)" in out


def test_a_dry_run_of_refresh_changes_nothing_in_the_projects(world):
    world.project("libft")
    libft = world.local("libft")
    world.commit("libft", "two")
    before = git("rev-parse", "HEAD", cwd=libft)
    code, out = world.run("refresh", CURSUS_DRY_RUN="1")
    assert code == 0 and "dry  libft: would pull 1 commit(s) of main" in out and git("rev-parse", "HEAD", cwd=libft) == before
    assert not (libft / "two.txt").exists()
    code, out = world.run("refresh")
    assert code == 0 and "pull libft: 1 commit(s)" in out


# ---------------------------------------------------------------- init


def fake_gh(world, *, logged_in=True):
    """A `gh` that creates the bare repository instead of GitHub, and records how it was called."""
    bin_dir = world.base / "bin"
    bin_dir.mkdir()
    log = world.base / "gh.log"
    gh = bin_dir / "gh"
    gh.write_text(f"""#!/bin/sh
echo "$@" >> {log}
case "$1 $2" in
    "auth status") exit {0 if logged_in else 1} ;;
    "repo view") exit 1 ;;
    "repo create") git init -q --bare -b main "{world.cursus}" ;;
esac
""")
    gh.chmod(0o755)
    return {"PATH": f"{bin_dir}:{ENV['PATH']}"}, log


def test_init_creates_the_github_repo_when_it_is_missing_and_gives_it_a_first_commit(world):
    env, log = fake_gh(world)
    code, out = world.run("init", **env)
    assert code == 0, out
    assert "repo create Rodolfo9898/42Cursus --private --description" in log.read_text()
    assert git("log", "--format=%s", cwd=world.cursus) == "Initial commit" and "common-core/" in git("show", "HEAD:README.md", cwd=world.cursus)
    assert "git clone --recurse-submodules git@github.com:Rodolfo9898/42Cursus.git" in git("show", "HEAD:README.md", cwd=world.cursus)
    assert world.leftovers() == [] and "is ready (private)" in out
    code, out = world.run("init", **env)                                                  # safe to run again
    assert code == 0 and "is ready on GitHub" in out and log.read_text().count("repo create") == 1


def test_init_fills_a_repo_that_exists_but_is_empty_without_creating_another(world):
    git("init", "-q", "--bare", "-b", "main", str(world.cursus), cwd=world.base)
    env, log = fake_gh(world)
    code, out = world.run("init", **env)
    assert code == 0 and "exists on GitHub but is empty" in out and not log.exists()
    assert git("log", "--format=%s", cwd=world.cursus) == "Initial commit"


def test_init_needs_the_github_cli_to_be_logged_in_and_checks_the_visibility(world):
    env, log = fake_gh(world, logged_in=False)
    code, out = world.run("init", **env)
    assert code == 1 and "not logged in" in out and "repo create" not in log.read_text()
    code, out = world.run("init", CURSUS_VISIBILITY="secret")
    assert code == 1 and "CURSUS_VISIBILITY must be private or public" in out


def test_a_dry_run_of_init_creates_nothing(world):
    env, log = fake_gh(world)
    code, out = world.run("init", CURSUS_DRY_RUN="1", **env)
    assert code == 0 and "would create Rodolfo9898/42Cursus" in out and not world.cursus.exists() and not log.exists()


# ---------------------------------------------------------------- make


def test_the_make_targets_and_the_usage_line_exist():
    makefile = (ROOT / "Makefile").read_text()
    for target, command in (("cursus-update", "update"), ("cursus-push", "push $(ONLY)"), ("cursus-refresh", "refresh $(ONLY)"),
                            ("cursus-sort", "sort $(MAP)"), ("cursus", "init")):
        assert f"\n{target}:\n\t@sh scripts/cursus.sh {command}\n" in makefile, target
        assert target in makefile.split(".PHONY:")[1].split()
    done = subprocess.run(["sh", str(SCRIPT), "nonsense"], capture_output=True, text=True)
    assert done.returncode == 2 and "| update | push [name ...] | refresh [name ...]" in done.stderr
