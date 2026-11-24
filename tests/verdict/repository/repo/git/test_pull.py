import subprocess

import pytest

from verdict.repository import repo


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


def test_a_real_clone_through_the_ssh_stand_in_has_its_history_and_files(pulled):
    _, clone, _ = pulled
    assert (clone / ".git").is_dir() and (clone / "a.c").read_text() == "int a;\n"


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


def test_pull_needs_a_remote(tmp_path):
    folder = tmp_path / "local"
    folder.mkdir()
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    with pytest.raises(repo.RepoError, match="no remote"):
        repo.pull(folder, tmp_path / "known_hosts")


def test_a_pull_that_git_refuses_says_pull_not_clone(tmp_path):
    folder = tmp_path / "p"
    (folder / ".git").mkdir(parents=True)

    def fake_run(cmd, **kwargs):
        if "config" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "remote.origin.url=git@github.com:me/x.git\n", "")
        return subprocess.CompletedProcess(cmd, 1, "", "fatal: Not possible to fast-forward, aborting.\n")

    puller = repo.Puller(repo.GitClient.networked(tmp_path / "known_hosts", global_config=False, runner=fake_run),
                         repo.FolderInspector(repo.GitClient.offline(fake_run)))
    with pytest.raises(repo.RepoError, match="git pull failed: fatal: Not possible to fast-forward"):
        puller.pull(folder)


def test_a_pull_that_takes_too_long_is_a_clear_error(tmp_path):
    folder = tmp_path / "p"
    (folder / ".git").mkdir(parents=True)

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    puller = repo.Puller(repo.GitClient.networked(tmp_path / "known_hosts", runner=fake_run), repo.FolderInspector(repo.GitClient.offline(fake_run)))
    with pytest.raises(repo.RepoError, match="git config timed out after 20s"):
        puller.pull(folder)
