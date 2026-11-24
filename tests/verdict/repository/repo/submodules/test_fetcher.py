"""Submodules downloaded for the build (bare repositories stand in for GitHub)."""

import os
import shutil
import subprocess

import pytest

from verdict.repository import repo
from verdict.repository.repo.submodules.fetcher import SubmoduleFetcher

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow", "GIT_CONFIG_VALUE_0": "always", "GIT_TERMINAL_PROMPT": "0"}
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


class AnythingLocal:
    """(the real rule only lets known hosts through: tested in test_policy)"""

    def source(self, url):
        return "file"


def git(*args, cwd):
    done = subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout.strip()


class Libs:
    """Libraries with a 'GitHub' each, a project that has them as submodules, and a copy of the project as the web app makes it
    (cloned without the submodules, so their folders are empty)."""

    def __init__(self, base):
        self.base = base
        for d in ("remotes", "work", "ws"):
            (base / d).mkdir()

    def lib(self, name, nested=None):
        work = self.base / "work" / name
        bare = self.base / "remotes" / f"{name}.git"
        git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.base)
        git("init", "-q", "-b", "main", str(work), cwd=self.base)
        (work / f"{name}.h").write_text(f"// {name}\n")
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "first", cwd=work)
        if nested:
            git("submodule", "add", "-q", str(self.base / "remotes" / f"{nested}.git"), f"deps/{nested}", cwd=work)
            git("commit", "-q", "-m", "with a lib of its own", cwd=work)
        git("remote", "add", "origin", str(bare), cwd=work)
        git("push", "-q", "origin", "main", cwd=work)
        return git("rev-parse", "HEAD", cwd=work)

    def advance(self, name):
        """The library moves on after the project recorded its commit."""
        work = self.base / "work" / name
        (work / "later.txt").write_text("later")
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "later", cwd=work)
        git("push", "-q", "origin", "main", cwd=work)

    def project(self, **libs):
        """libs: name -> path inside the project."""
        project = self.base / "work" / "project"
        git("init", "-q", "-b", "main", str(project), cwd=self.base)
        (project / "Makefile").write_text("all:\n")
        for name, path in libs.items():
            git("submodule", "add", "-q", str(self.base / "remotes" / f"{name}.git"), path, cwd=project)
        git("add", "-A", cwd=project)
        git("commit", "-q", "-m", "project", "--allow-empty", cwd=project)
        copy = self.base / "copy"
        git("clone", "-q", "--no-recurse-submodules", str(project), str(copy), cwd=self.base)
        return copy

    def fetch(self, copy, **kw):
        known_hosts = self.base / "ws" / "known_hosts"
        client = repo.GitClient.networked(known_hosts, global_config=False, protocols=("file",))
        return SubmoduleFetcher(client, AnythingLocal(), protocols=("file",), **kw).fetch(copy)


@pytest.fixture
def libs(tmp_path, monkeypatch):
    for key, value in GIT_ENV.items():
        if key.startswith("GIT_"):
            monkeypatch.setenv(key, value)
    return Libs(tmp_path)


@needs_git
def test_the_libs_are_downloaded_at_the_commits_the_project_records_so_the_build_needs_no_network(libs):
    ft, mlx = libs.lib("libft"), libs.lib("mlx")
    copy = libs.project(libft="libs/libft", mlx="libs/mlx")
    libs.advance("libft")                                                   # GitHub has moved on since the project recorded its commit
    assert not any((copy / "libs" / "libft").iterdir())
    notes = libs.fetch(copy)
    assert [(n.path, n.ok) for n in notes] == [("libs/libft", True), ("libs/mlx", True)] and notes[0].message == f"downloaded at {ft[:7]}"
    assert git("rev-parse", "HEAD", cwd=copy / "libs" / "libft") == ft and (copy / "libs" / "libft" / "libft.h").is_file()
    assert git("rev-parse", "HEAD", cwd=copy / "libs" / "mlx") == mlx and not (copy / "libs" / "libft" / "later.txt").exists()
    shutil.rmtree(libs.base / "remotes")                                    # no 'GitHub' any more: what the Makefile's own rule would do now
    done = subprocess.run(["git", "submodule", "update", "--init"], cwd=copy, env=GIT_ENV, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


@needs_git
def test_a_lib_with_a_lib_of_its_own_is_downloaded_too_but_not_forever(libs):
    libs.lib("deepest")
    libs.lib("deep", nested="deepest")
    libs.lib("mid", nested="deep")
    copy = libs.project(mid="libs/mid")
    notes = libs.fetch(copy)
    assert [(n.path, n.ok) for n in notes] == [("libs/mid", True), ("libs/mid/deps/deep", True)]           # two levels
    assert (copy / "libs" / "mid" / "deps" / "deep" / "deep.h").is_file()
    assert not any((copy / "libs" / "mid" / "deps" / "deep" / "deps" / "deepest").iterdir())               # the third is left to the build


@needs_git
def test_a_folder_that_already_has_content_is_left_alone(libs):
    libs.lib("libft")
    copy = libs.project(libft="libs/libft")
    (copy / "libs" / "libft" / "mine.c").write_text("kept\n")
    notes = libs.fetch(copy)
    assert [(n.ok, n.message) for n in notes] == [(True, "already there")] and sorted(p.name for p in (copy / "libs" / "libft").iterdir()) == ["mine.c"]


@needs_git
def test_a_lib_that_cannot_be_downloaded_is_reported_and_leaves_its_folder_empty_and_the_others_are_still_done(libs):
    libs.lib("libft"), libs.lib("mlx")
    copy = libs.project(libft="libs/libft", mlx="libs/mlx")
    shutil.rmtree(libs.base / "remotes" / "libft.git")
    notes = libs.fetch(copy)
    by_path = {n.path: n for n in notes}
    assert not by_path["libs/libft"].ok and "libft.git" in by_path["libs/libft"].message and by_path["libs/mlx"].ok
    assert list((copy / "libs" / "libft").iterdir()) == [] and (copy / "libs" / "mlx" / "mlx.h").is_file()


@needs_git
def test_a_commit_the_download_does_not_contain_is_reported(libs):
    libs.lib("libft")
    copy = libs.project(libft="libs/libft")
    git("update-index", "--cacheinfo", "160000", "1" * 40, "libs/libft", cwd=copy)          # the project records a commit nobody ever pushed
    notes = libs.fetch(copy)
    assert not notes[0].ok and "1111111 the project records is not in it" in notes[0].message


@needs_git
def test_addresses_this_app_does_not_download_from_are_never_contacted(libs, tmp_path):
    libs.lib("libft")
    copy = libs.project(libft="libs/libft")
    marker = tmp_path / "ran"
    for url in (str(libs.base / "remotes" / "libft.git"), f"ext::sh -c 'touch {marker}'", "--upload-pack=touch x", "http://github.com/a/b.git",
                "https://internal.example/a/b.git", "https://github.com.evil.example/a/b.git", "https://github.com/../b.git", ""):
        git("config", "-f", ".gitmodules", "submodule.libs/libft.url", url, cwd=copy)
        notes = repo.fetch_submodules(copy, libs.base / "ws" / "known_hosts")                 # the real rule, the real protocols
        assert not notes[0].ok and ("not an address this app downloads from" in notes[0].message or "gives no address" in notes[0].message), url
        assert list((copy / "libs" / "libft").iterdir()) == [] and not marker.exists()


@needs_git
def test_folder_names_this_app_will_not_write_to_and_links_are_refused(libs, tmp_path):
    libs.lib("libft"), libs.lib("mlx")
    copy = libs.project(libft="my libs/libft", mlx="libs/mlx")
    spaced = {n.path: n for n in libs.fetch(copy)}["my libs/libft"]
    assert not spaced.ok and "folder name is not one this app will write to" in spaced.message
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    shutil.rmtree(copy / "libs" / "mlx")
    (copy / "libs" / "mlx").symlink_to(outside)
    notes = {n.path: n for n in libs.fetch(copy)}
    assert not notes["libs/mlx"].ok and "link" in notes["libs/mlx"].message and list(outside.iterdir()) == []


@needs_git
def test_no_more_than_ten_and_no_more_time_than_the_budget(libs):
    for i in range(12):
        libs.lib(f"lib{i:02d}")
    copy = libs.project(**{f"lib{i:02d}": f"libs/lib{i:02d}" for i in range(12)})
    notes = libs.fetch(copy)
    assert sum(n.ok for n in notes) == repo.MAX_SUBMODULES and all("more than 10 submodules" in n.message for n in notes if not n.ok) and len(notes) == 12
    for i in range(12):                                                     # (the copy above is reused: empty it again)
        shutil.rmtree(copy / "libs" / f"lib{i:02d}")
        (copy / "libs" / f"lib{i:02d}").mkdir()
    ticks = iter([0.0] + [1000.0] * 100)
    late = libs.fetch(copy, clock=lambda: next(ticks))
    assert not any(n.ok for n in late) and sum("ran out of time" in n.message for n in late) == repo.MAX_SUBMODULES


def test_a_project_whose_submodules_cannot_be_read_gets_one_note_and_no_error(tmp_path):
    def broken(cmd, **kwargs):
        raise OSError("git is gone")

    fetcher = SubmoduleFetcher(repo.GitClient({"PATH": "/usr/bin"}, broken), AnythingLocal())
    notes = fetcher.fetch(tmp_path)
    assert [(n.path, n.ok) for n in notes] == [("", False)] and "could not read the submodules: git is gone" in notes[0].message


def test_a_project_without_submodules_has_no_notes(tmp_path):
    (tmp_path / "plain").mkdir()
    git("init", "-q", "-b", "main", str(tmp_path / "plain"), cwd=tmp_path)
    assert repo.fetch_submodules(tmp_path / "plain", tmp_path / "ws" / "known_hosts") == []
