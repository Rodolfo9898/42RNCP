import subprocess

import pytest

from verdict.repository import repo
from verdict.repository.repo.git.clone import Cloner

DENIED = "Cloning into 'x'...\ngit@github.com: Permission denied (publickey).\nfatal: Could not read from remote repository.\n"


def cloner_with(tmp_path, fake_run, pauses=None):
    """A Cloner whose git is `fake_run`: the commands it would run go to the fake, nothing reaches a server."""
    known_hosts = tmp_path / "ws" / "known_hosts"
    inspector = repo.FolderInspector(repo.GitClient.offline(fake_run))
    return Cloner(repo.GitClient.networked(known_hosts, runner=fake_run), inspector, sleep=(pauses.append if pauses is not None else lambda s: None))


def test_clone_uses_ssh_agent_and_never_prompts(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if "clone" in cmd:
            (tmp_path / "projects" / "42" / "ps").mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "abc1234\nsubject\nauthor\n", "")

    monkeypatch.setenv("SSH_AUTH_SOCK", "/run/agent.sock")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-leak")
    info = cloner_with(tmp_path, fake_run).clone("git@github.com:user/repo.git", tmp_path / "projects" / "42" / "ps")
    assert (info.url, info.commit, info.subject, info.author) == ("git@github.com:user/repo.git", "abc1234", "subject", "author")

    cmd, kwargs = calls[0]
    assert cmd[:2] == ["git", "-c"] and cmd[-3:-1] == ["--", "git@github.com:user/repo.git"]
    assert "protocol.ssh.allow=always" in cmd and "protocol.allow=never" in cmd
    assert "core.hooksPath=/dev/null" in cmd
    assert not any(arg.startswith("--depth") or arg.startswith("--shallow") for arg in cmd)    # a full clone, whole history
    env = kwargs["env"]
    assert env["SSH_AUTH_SOCK"] == "/run/agent.sock"
    assert "BatchMode=yes" in env["GIT_SSH_COMMAND"] and "StrictHostKeyChecking=accept-new" in env["GIT_SSH_COMMAND"]
    assert str(tmp_path / "ws" / "known_hosts") in env["GIT_SSH_COMMAND"]
    assert "GITHUB_TOKEN" not in env


def test_clone_failure_reports_the_last_git_line_and_cleans_up(tmp_path):
    dest = tmp_path / "projects" / "ps"

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 128, "", "Cloning...\ngit@github.com: Permission denied (publickey).\n")

    with pytest.raises(repo.RepoError, match="Permission denied"):
        cloner_with(tmp_path, fake_run).clone("git@github.com:user/private.git", dest)
    assert not dest.exists()


def test_clone_refuses_an_existing_destination(tmp_path):
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "precious").write_text("do not delete")
    with pytest.raises(repo.RepoError):
        repo.clone("git@github.com:user/repo.git", tmp_path / "keep", tmp_path / "known_hosts")
    assert (tmp_path / "keep" / "precious").read_text() == "do not delete"


def test_clone_refuses_an_address_that_is_not_ssh(tmp_path):
    with pytest.raises(repo.RepoError, match="Only SSH"):
        repo.clone("https://github.com/user/repo.git", tmp_path / "dest", tmp_path / "known_hosts")
    assert not (tmp_path / "dest").exists()


def test_a_clone_that_takes_too_long_is_stopped_and_cleaned_up(tmp_path):
    dest = tmp_path / "projects" / "ps"

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True, exist_ok=True)
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    with pytest.raises(repo.RepoError, match="timed out after 300s"):
        cloner_with(tmp_path, fake_run).clone("git@github.com:user/repo.git", dest)
    assert not dest.exists()


# ---------------------------------------------------------------- a refused sign-in: one more try


def clone_with(tmp_path, clone_results, url="git@github.com:user/repo.git", pauses=None):
    """Clones with a fake git. clone_results: what each clone attempt answers (stderr, or "" for success)."""
    dest = tmp_path / "projects" / "ps"
    seen = {"clones": 0, "other": []}

    def fake_run(cmd, **kwargs):
        if "clone" not in cmd:
            seen["other"].append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "abc1234\nsubject\nauthor\n", "")
        stderr = clone_results[min(seen["clones"], len(clone_results) - 1)]
        seen["clones"] += 1
        dest.mkdir(parents=True, exist_ok=True)         # git leaves a half-made folder behind when it fails
        return subprocess.CompletedProcess(cmd, 128 if stderr else 0, "", stderr)

    try:
        return cloner_with(tmp_path, fake_run, pauses).clone(url, dest), seen, dest
    except repo.RepoError as exc:
        return exc, seen, dest


def test_a_sign_in_that_fails_once_and_works_the_second_time_is_a_success(tmp_path):
    result, seen, dest = clone_with(tmp_path, [DENIED, ""])
    assert isinstance(result, repo.RepoInfo) and result.commit == "abc1234" and seen["clones"] == 2
    assert dest.exists()


def test_it_only_tries_twice_and_a_refused_key_that_stays_refused_gets_the_ordinary_explanation(tmp_path):
    error, seen, dest = clone_with(tmp_path, [DENIED])
    assert isinstance(error, repo.RepoError) and seen["clones"] == 2 and not dest.exists()
    assert "Permission denied (publickey)" in str(error) and "Check the 'ssh' indicator" in str(error)


def test_other_failures_are_not_retried(tmp_path):
    error, seen, _ = clone_with(tmp_path, ["Host key verification failed.\n"])
    assert seen["clones"] == 1 and "known_hosts" in str(error)
    error, seen, _ = clone_with(tmp_path, ["ERROR: Repository not found.\nfatal: Could not read from remote repository.\n"])
    assert seen["clones"] == 1 and "Repository not found" in str(error)
    error, seen, _ = clone_with(tmp_path, ["fatal: unable to access: Could not resolve hostname nowhere.example\n"])
    assert seen["clones"] == 1 and "no DNS/network access" in str(error)


def test_a_dropped_connection_is_retried_too(tmp_path):
    result, seen, _ = clone_with(tmp_path, ["Connection closed by 20.26.156.215 port 22\nfatal: Could not read from remote repository.\n", ""])
    assert isinstance(result, repo.RepoInfo) and seen["clones"] == 2


def test_the_second_try_waits_a_moment_first(tmp_path):
    pauses = []
    clone_with(tmp_path, [DENIED, ""], pauses=pauses)
    assert pauses == [Cloner.PAUSE] == [2]


@pytest.mark.parametrize("stderr,transient", [("Permission denied (publickey).", True), ("Connection reset by peer", True),
                                              ("kex_exchange_identification: read: Connection reset", True), ("Operation timed out", True),
                                              ("Repository not found.", False), ("Host key verification failed.", False)])
def test_which_failures_look_like_the_connection(stderr, transient):
    assert repo.is_transient(stderr) is transient


def test_an_unexplained_failure_still_says_what_git_said():
    assert repo.explain_clone_failure("", 128) == "git clone failed: no error output (exit code 128)"
    assert repo.explain_clone_failure("Cloning into 'x'...\nfatal: boom\n", 1) == "git clone failed: fatal: boom"
