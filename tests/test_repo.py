import subprocess

import pytest

from verdict import repo


@pytest.mark.parametrize("url", [
    "git@github.com:user/repo.git",
    "git@github.com:user/repo",
    "git@vogsphere.42lisboa.com:vogsphere/intra-uuid-1234-abcd-56789",
    "ssh://git@github.com/user/repo.git",
    "ssh://git@gitlab.example.org:2222/group/sub-group/repo.git",
])
def test_ssh_urls_are_accepted(url):
    assert repo.validate_url(f"  {url}  ") == url


def test_clone_uses_ssh_agent_and_never_prompts(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[:2] == ["git", "-c"] and "clone" in cmd:
            (tmp_path / "projects" / "42" / "ps").mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "abc1234\nsubject\nauthor\n", "")

    monkeypatch.setattr(repo.subprocess, "run", fake_run)
    monkeypatch.setenv("SSH_AUTH_SOCK", "/run/agent.sock")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-leak")
    info = repo.clone("git@github.com:user/repo.git", tmp_path / "projects" / "42" / "ps", tmp_path / "ws" / "known_hosts")
    assert (info.commit, info.subject, info.author) == ("abc1234", "subject", "author")

    cmd, kwargs = calls[0]
    assert cmd[-3:-1] == ["--", "git@github.com:user/repo.git"]
    assert "protocol.ssh.allow=always" in cmd and "protocol.allow=never" in cmd
    assert "core.hooksPath=/dev/null" in cmd
    assert not any(arg.startswith("--depth") or arg.startswith("--shallow") for arg in cmd)    # a full clone, whole history
    env = kwargs["env"]
    assert env["SSH_AUTH_SOCK"] == "/run/agent.sock"
    assert "BatchMode=yes" in env["GIT_SSH_COMMAND"] and "StrictHostKeyChecking=accept-new" in env["GIT_SSH_COMMAND"]
    assert str(tmp_path / "ws" / "known_hosts") in env["GIT_SSH_COMMAND"]
    assert "GITHUB_TOKEN" not in env


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(repo, "RETRY_PAUSE", 0)


def test_clone_failure_reports_the_last_git_line_and_cleans_up(tmp_path, monkeypatch):
    dest = tmp_path / "projects" / "ps"

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            dest.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 128, "", "Cloning...\ngit@github.com: Permission denied (publickey).\n")

    monkeypatch.setattr(repo.subprocess, "run", fake_run)
    with pytest.raises(repo.RepoError, match="Permission denied"):
        repo.clone("git@github.com:user/private.git", dest, tmp_path / "ws" / "known_hosts")
    assert not dest.exists()


@pytest.mark.parametrize("url,expected", [
    ("git@github.com:user/push_swap.git", "push_swap"),
    ("ssh://git@host:22/group/my-repo", "my-repo"),
    ("git@vogsphere.42lisboa.com:vogsphere/intra-uuid-1234", "intra-uuid-1234"),
])
def test_default_name(url, expected):
    assert repo.default_name(url) == expected


def test_resolve_destination_builds_a_path_inside_the_root(tmp_path):
    assert repo.resolve_destination(tmp_path, "42/common-core", "push_swap") == tmp_path.resolve() / "42" / "common-core" / "push_swap"
    assert repo.resolve_destination(tmp_path, "", "libft") == tmp_path.resolve() / "libft"
    assert repo.resolve_destination(tmp_path, "/".join(["a"]) + "/", "x") == tmp_path.resolve() / "a" / "x"


@pytest.mark.parametrize("destination,name", [
    ("..", "x"), ("a/../..", "x"), ("/etc", "x"), ("~/x", "x"), ("a\\b", "x"), ("a b", "x"), (".hidden/../x", "x"),
    ("", ""), ("", ".."), ("", "-rf"), ("", "a/b"), ("", "x" * 101),
])
def test_resolve_destination_rejects_escapes_and_bad_names(tmp_path, destination, name):
    with pytest.raises(repo.RepoError):
        repo.resolve_destination(tmp_path, destination, name)


def test_resolve_destination_refuses_to_overwrite(tmp_path):
    (tmp_path / "libft").mkdir()
    with pytest.raises(repo.RepoError, match="already exists"):
        repo.resolve_destination(tmp_path, "", "libft")


def test_resolve_destination_blocks_symlinked_folders_leaving_the_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "projects"
    root.mkdir()
    (root / "escape").symlink_to(outside)
    with pytest.raises(repo.RepoError):
        repo.resolve_destination(root, "escape", "x")


def test_clone_refuses_an_existing_destination(tmp_path):
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "precious").write_text("do not delete")
    with pytest.raises(repo.RepoError):
        repo.clone("git@github.com:user/repo.git", tmp_path / "keep", tmp_path / "known_hosts")
    assert (tmp_path / "keep" / "precious").read_text() == "do not delete"


def test_list_folders_suggests_only_plain_folders(tmp_path):
    (tmp_path / "42" / "common-core").mkdir(parents=True)
    (tmp_path / "42" / "common-core" / "deep" / "deeper").mkdir(parents=True)
    (tmp_path / "libft" / ".git").mkdir(parents=True)
    assert repo.list_folders(tmp_path) == ["42", "42/common-core"]  # two levels deep, no repos


def test_list_existing_marks_repositories_and_does_not_search_inside_them(tmp_path):
    (tmp_path / "libft" / ".git").mkdir(parents=True)
    (tmp_path / "libft" / "src").mkdir()
    (tmp_path / "42" / "push_swap").mkdir(parents=True)
    (tmp_path / ".hidden").mkdir()
    assert repo.list_existing(tmp_path) == [
        {"path": "42", "git": False}, {"path": "42/push_swap", "git": False}, {"path": "libft", "git": True}]


def test_use_existing_accepts_a_folder_and_reads_its_git_state(tmp_path):
    folder = tmp_path / "42" / "libft"
    folder.mkdir(parents=True)
    git = ["git", "-C", str(folder)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "remote", "add", "origin", "git@github.com:me/libft.git"], check=True)
    (folder / "a.c").write_text("int a;\n")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "-c", "user.name=Me", "-c", "user.email=m@e", "commit", "-qm", "first"], check=True)
    path, info = repo.use_existing(tmp_path, "42/libft")
    assert path == tmp_path.resolve() / "42" / "libft"
    assert (info.url, info.subject, info.author) == ("git@github.com:me/libft.git", "first", "Me") and info.commit
    assert (folder / "a.c").read_text() == "int a;\n"             # nothing touched


def test_use_existing_accepts_a_plain_folder_without_git(tmp_path):
    (tmp_path / "plain").mkdir()
    _, info = repo.use_existing(tmp_path, "plain")
    assert info == repo.RepoInfo(url="", commit="", subject="", author="")


@pytest.mark.parametrize("rel", ["", "/", "../outside", "a/../../x", "/etc", "~", "missing", "a\\b", ".git"])
def test_use_existing_rejects_escapes_and_missing_folders(tmp_path, rel):
    (tmp_path / "a").mkdir()
    with pytest.raises(repo.RepoError):
        repo.use_existing(tmp_path, rel)


def test_use_existing_refuses_symlinks_leaving_the_root(tmp_path):
    outside, root = tmp_path / "outside", tmp_path / "root"
    outside.mkdir(); root.mkdir()
    (root / "escape").symlink_to(outside)
    with pytest.raises(repo.RepoError):
        repo.use_existing(root, "escape")


def _git(folder, *args):
    subprocess.run(["git", "-C", str(folder), "-c", "user.name=Me", "-c", "user.email=m@e", *args],
                   check=True, capture_output=True)


@pytest.fixture
def pulled(tmp_path, monkeypatch):
    """A clone of git@example.com:me/libft.git whose 'ssh' is a stand-in that serves a local bare repository."""
    server = tmp_path / "server"
    (server / "me").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(server / "me" / "libft.git")], check=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ssh").write_text(f'#!/bin/sh\nfor last; do :; done\ncd "{server}" && eval "$last"\n')
    (bin_dir / "ssh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    author = tmp_path / "author"
    subprocess.run(["git", "init", "-q", "-b", "main", str(author)], check=True)
    _git(author, "remote", "add", "origin", "git@example.com:me/libft.git")
    (author / "a.c").write_text("int a;\n")
    _git(author, "add", ".")
    _git(author, "commit", "-qm", "first")
    _git(author, "push", "-q", "origin", "main")
    clone = tmp_path / "projects" / "libft"
    repo.clone("git@example.com:me/libft.git", clone, tmp_path / "ws" / "known_hosts")
    return author, clone, tmp_path / "ws" / "known_hosts"


def test_pull_fast_forwards_to_the_new_commit(pulled):
    author, clone, known_hosts = pulled
    (author / "b.c").write_text("int b;\n")
    _git(author, "add", ".")
    _git(author, "commit", "-qm", "second")
    _git(author, "push", "-q", "origin", "main")
    info, _ = repo.pull(clone, known_hosts)
    assert info.subject == "second" and (clone / "b.c").read_text() == "int b;\n"
    info, summary = repo.pull(clone, known_hosts)
    assert info.subject == "second" and "up to date" in summary.lower()


@pytest.mark.parametrize("key", ["core.sshCommand", "core.fsmonitor", "filter.x.smudge", "include.path", "core.pager"])
def test_pull_refuses_a_config_that_could_run_commands(pulled, key):
    _, clone, known_hosts = pulled
    _git(clone, "config", key, "touch /tmp/pwned")
    with pytest.raises(repo.RepoError, match="could run commands"):
        repo.pull(clone, known_hosts)


def test_pull_refuses_a_remote_that_is_not_an_ssh_address(pulled):
    _, clone, known_hosts = pulled
    _git(clone, "remote", "add", "other", "ext::sh -c touch% /tmp/pwned")
    with pytest.raises(repo.RepoError, match="Only SSH"):
        repo.pull(clone, known_hosts)


def test_pull_needs_a_git_repository(tmp_path):
    (tmp_path / "plain").mkdir()
    with pytest.raises(repo.RepoError, match="not a git repository"):
        repo.pull(tmp_path / "plain", tmp_path / "known_hosts")


# ---------------------------------------------------------------- a refused sign-in: one more try, then say what ssh did


OFFERED_TWO = """debug1: Will attempt key: me@mac ED25519 SHA256:aaaa agent
debug1: Offering public key: me@mac ED25519 SHA256:aaaa agent
debug1: Authentications that can continue: publickey
debug1: Offering public key: me@mac ED25519 SHA256:bbbb agent
debug1: Authentications that can continue: publickey
git@github.com: Permission denied (publickey).
"""
DENIED = "Cloning into 'x'...\ngit@github.com: Permission denied (publickey).\nfatal: Could not read from remote repository.\n"


def clone_with(tmp_path, monkeypatch, clone_results, probe_stderr="", probe_stdout="", url="git@github.com:user/repo.git", probe_raises=None):
    """Runs repo.clone with fake git and ssh. clone_results: what each git clone attempt answers (stderr, or "" for success)."""
    dest = tmp_path / "projects" / "ps"
    seen = {"clones": 0, "probes": []}

    def fake_run(cmd, **kwargs):
        if cmd[0] == "ssh":
            seen["probes"].append((cmd, kwargs))
            if probe_raises:
                raise probe_raises
            return subprocess.CompletedProcess(cmd, 255, probe_stdout, probe_stderr)
        if "clone" in cmd:
            stderr = clone_results[min(seen["clones"], len(clone_results) - 1)]
            seen["clones"] += 1
            if stderr:
                dest.mkdir(parents=True, exist_ok=True)         # git leaves a half-made folder behind
                return subprocess.CompletedProcess(cmd, 128, "", stderr)
            dest.mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0, "abc1234\nsubject\nauthor\n", "")

    monkeypatch.setattr(repo.subprocess, "run", fake_run)
    monkeypatch.setenv("SSH_AUTH_SOCK", "/run/agent.sock")
    try:
        return repo.clone(url, dest, tmp_path / "ws" / "known_hosts"), seen, dest
    except repo.RepoError as exc:
        return exc, seen, dest


def test_a_sign_in_that_fails_once_and_works_the_second_time_is_a_success(tmp_path, monkeypatch):
    result, seen, dest = clone_with(tmp_path, monkeypatch, [DENIED, ""])
    assert isinstance(result, repo.RepoInfo) and result.commit == "abc1234" and seen["clones"] == 2 and seen["probes"] == []
    assert dest.exists()


def test_it_only_tries_twice_and_a_refused_key_that_stays_refused_gets_a_diagnosis(tmp_path, monkeypatch):
    error, seen, dest = clone_with(tmp_path, monkeypatch, [DENIED], probe_stderr=OFFERED_TWO)
    assert isinstance(error, repo.RepoError) and seen["clones"] == 2 and len(seen["probes"]) == 1 and not dest.exists()
    text = str(error)
    assert "github.com accepted none of the 2 key(s) the ssh-agent offered: SHA256:aaaa (me@mac), SHA256:bbbb (me@mac)" in text
    assert "https://github.com/settings/keys" in text and "ssh-keygen -lf" in text
    assert "Check the 'ssh' indicator" not in text                                      # the generic guess is replaced by what was found


def test_the_probe_signs_in_the_way_the_clone_does_and_cannot_be_turned_into_a_command(tmp_path, monkeypatch):
    _, seen, _ = clone_with(tmp_path, monkeypatch, [DENIED], probe_stderr=OFFERED_TWO, url="ssh://git@gitlab.example.org:2222/group/repo.git")
    cmd, kwargs = seen["probes"][0]
    assert cmd[:3] == ["ssh", "-v", "-T"] and cmd[-3:] == ["-p", "2222", "git@gitlab.example.org"] and "BatchMode=yes" in cmd
    assert f"UserKnownHostsFile={tmp_path / 'ws' / 'known_hosts'}" in cmd and "GIT_SSH_COMMAND" not in kwargs["env"]
    assert kwargs["env"]["SSH_AUTH_SOCK"] == "/run/agent.sock" and kwargs["timeout"] <= 30 and kwargs.get("shell") is not True
    assert "github.com/settings/keys" not in str(clone_with(tmp_path / "again", monkeypatch, [DENIED], probe_stderr=OFFERED_TWO, url="ssh://git@gitlab.example.org:2222/group/repo.git")[0])


@pytest.mark.parametrize("log,expected", [
    ("", "offered no key to github.com at all"),
    ("debug1: Offering public key: me@mac ED25519 SHA256:aaaa agent\ndebug1: Server accepts key: me@mac ED25519 SHA256:aaaa agent\n"
     "git@github.com: Permission denied (publickey).\n", "github.com knows one of the keys the agent offered, but the agent did not sign with it: SHA256:aaaa"),
    ("debug1: Offering public key: me@mac ED25519 SHA256:aaaa agent\ndebug1: Server accepts key: me@mac ED25519 SHA256:aaaa agent\n"
     "Authenticated to github.com ([1.2.3.4]:22) using \"publickey\".\nHi Rodolfo9898! You've successfully authenticated\n",
     "github.com did accept your key and signed in as Rodolfo9898, so this account cannot read this repository"),
])
def test_what_ssh_did_is_told_in_plain_words(tmp_path, monkeypatch, log, expected):
    error, _, _ = clone_with(tmp_path, monkeypatch, [DENIED], probe_stderr=log)
    assert expected in str(error)


def test_if_the_probe_cannot_run_the_ordinary_message_is_kept(tmp_path, monkeypatch):
    for raises in (FileNotFoundError("ssh"), subprocess.TimeoutExpired("ssh", 30)):
        error, _, _ = clone_with(tmp_path, monkeypatch, [DENIED], probe_raises=raises)
        assert "Permission denied (publickey)" in str(error) and "Check the 'ssh' indicator" in str(error), raises


def test_other_failures_are_neither_retried_nor_probed(tmp_path, monkeypatch):
    error, seen, _ = clone_with(tmp_path, monkeypatch, ["Host key verification failed.\n"])
    assert seen["clones"] == 1 and seen["probes"] == [] and "known_hosts" in str(error)
    error, seen, _ = clone_with(tmp_path, monkeypatch, ["ERROR: Repository not found.\nfatal: Could not read from remote repository.\n"])
    assert seen["clones"] == 1 and seen["probes"] == [] and "Repository not found" in str(error)


def test_a_dropped_connection_is_retried_too(tmp_path, monkeypatch):
    result, seen, _ = clone_with(tmp_path, monkeypatch, ["Connection closed by 20.26.156.215 port 22\nfatal: Could not read from remote repository.\n", ""])
    assert isinstance(result, repo.RepoInfo) and seen["clones"] == 2


@pytest.mark.parametrize("url,expected", [
    ("git@github.com:user/repo.git", ("git", "github.com", None)),
    ("ssh://git@gitlab.example.org:2222/group/repo.git", ("git", "gitlab.example.org", 2222)),
    ("ssh://me@host/repo", ("me", "host", None)),
    ("me@vogsphere.42lisboa.com:vogsphere/intra-uuid-1234", ("me", "vogsphere.42lisboa.com", None)),
])
def test_user_host_and_port_come_out_of_an_address(url, expected):
    assert repo.ssh_target(repo.validate_url(url)) == expected


def test_the_second_try_waits_a_moment_first(tmp_path, monkeypatch):
    pauses = []
    monkeypatch.setattr(repo, "RETRY_PAUSE", 2)
    monkeypatch.setattr(repo.time, "sleep", pauses.append)
    clone_with(tmp_path, monkeypatch, [DENIED, ""])
    assert pauses == [2]


# ---------------------------------------------------------------- submodules downloaded for the build (bare repositories stand in for GitHub)


import os
import shutil

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow", "GIT_CONFIG_VALUE_0": "always", "GIT_TERMINAL_PROMPT": "0"}
ANYTHING_LOCAL = lambda url, hosts: "file"                  # (the real rule only lets known hosts through: tested below)
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


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
        kw.setdefault("allow", ANYTHING_LOCAL)
        kw.setdefault("protocols", ("file",))
        return repo.fetch_submodules(copy, self.base / "ws" / "known_hosts", **kw)


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
    late = libs.fetch(copy, _clock=lambda: next(ticks))
    assert not any(n.ok for n in late) and sum("ran out of time" in n.message for n in late) == repo.MAX_SUBMODULES


def test_the_hosts_a_submodule_may_come_from():
    ok = {"https://github.com/Rodolfo9898/libft.git": "https", "https://gitlab.com/a/b": "https", "git@github.com:Rodolfo9898/libft.git": "ssh",
          "ssh://git@bitbucket.org/a/b.git": "ssh", "https://codeberg.org/a/b": "https", "git@vogsphere.42lisboa.com:vogsphere/x": None,
          "https://GitHub.com/a/b.git": "https"}
    for url, expected in ok.items():
        assert repo.submodule_source(url) == expected, url
    assert repo.submodule_source("git@vogsphere.42lisboa.com:vogsphere/x", {"vogsphere.42lisboa.com"}) == "ssh"       # the project's own host
    for bad in ("http://github.com/a/b", "file:///etc", "/etc/passwd", "../x", "ext::sh -c x", "-oProxyCommand=x", "https://github.com:8080/a/b",
                "https://github.com@evil.example/a/b", "https://evil.example/github.com/a/b", "git@github.com:a/../b", "github.com/a/b"):
        assert repo.submodule_source(bad) is None, bad


def test_a_private_github_lib_is_retried_through_the_agent_and_only_there(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "clone" in cmd and cmd[cmd.index("--") + 1].startswith("https://"):
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: could not read Username for 'https://github.com': terminal prompts disabled\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(repo.subprocess, "run", fake_run)
    root = tmp_path / "p"
    (root / "libs" / "libft").mkdir(parents=True)
    env = {"PATH": "/usr/bin", "SSH_AUTH_SOCK": "/run/agent.sock"}
    args = (root, "libs/libft", "a" * 40, "https://github.com/Rodolfo9898/libft.git", "libs/libft", env, frozenset(), ("https", "ssh"), repo.submodule_source, 10**9, lambda: 0.0)
    note = repo._fetch_one(*args)
    clones = [c[c.index("--") + 1] for c in calls if "clone" in c]
    assert note.ok and clones == ["https://github.com/Rodolfo9898/libft.git", "git@github.com:Rodolfo9898/libft.git"]
    calls.clear()
    other = ("https://gitlab.com/a/b.git",)
    note = repo._fetch_one(root, "libs/libft", "a" * 40, other[0], "libs/libft", env, frozenset(), ("https", "ssh"), repo.submodule_source, 10**9, lambda: 0.0)
    assert [c[c.index("--") + 1] for c in calls if "clone" in c] == ["https://gitlab.com/a/b.git"]                    # only github.com gets the second try
    calls.clear()
    note = repo._fetch_one(root, "libs/libft", "a" * 40, "https://github.com/a/b.git", "libs/libft", {"PATH": "/usr/bin"}, frozenset(), ("https", "ssh"), repo.submodule_source, 10**9, lambda: 0.0)
    assert not note.ok and [c[c.index("--") + 1] for c in calls if "clone" in c] == ["https://github.com/a/b.git"]  # no agent, no second try
    cmd = next(c for c in calls if "clone" in c)
    assert "credential.helper=" in cmd and "protocol.allow=never" in cmd and "core.hooksPath=/dev/null" in cmd


def test_submodule_folders_are_read_as_text_and_empty_ones_are_found(tmp_path):
    (tmp_path / ".gitmodules").write_text('[submodule "a"]\n\tpath = libs/a\n\turl = x\n[submodule "b"]\n\tpath = libs/b\n[submodule "c"]\n\tpath = ../escape\n[submodule "d"]\n\tpath = has space/d\n')
    (tmp_path / "libs" / "a").mkdir(parents=True)
    (tmp_path / "libs" / "b").mkdir()
    (tmp_path / "libs" / "b" / "full.c").write_text("x")
    assert repo.submodule_paths(tmp_path) == ["libs/a", "libs/b"]
    assert repo.empty_submodules(tmp_path) == ["libs/a"]
    assert repo.submodule_paths(tmp_path / "nowhere") == [] and repo.empty_submodules(tmp_path / "nowhere") == []


def test_a_ssh_address_needs_the_agent_and_is_not_even_tried_without_it(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(repo.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    root = tmp_path / "p"
    (root / "libs" / "libft").mkdir(parents=True)
    note = repo._fetch_one(root, "libs/libft", "a" * 40, "git@github.com:Rodolfo9898/libft.git", "libs/libft", {"PATH": "/usr/bin"}, frozenset(),
                           ("https", "ssh"), repo.submodule_source, 10**9, lambda: 0.0)
    assert not note.ok and "needs your ssh-agent" in note.message and calls == []
