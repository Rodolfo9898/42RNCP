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


def test_clone_failure_reports_the_last_git_line_and_cleans_up(tmp_path, monkeypatch):
    dest = tmp_path / "projects" / "ps"

    def fake_run(cmd, **kwargs):
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
