import subprocess

from verdict.repository import repo
from verdict.repository.repo.submodules.download import SubmoduleDownload
from verdict.repository.repo.submodules.policy import HostPolicy


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


def test_the_policy_is_a_strategy_the_download_asks():
    assert HostPolicy().source("https://github.com/a/b.git") == "https"
    assert HostPolicy({"git.school.example"}).source("https://git.school.example/a/b.git") == "https"
    assert HostPolicy().source("https://git.school.example/a/b.git") is None


def test_a_private_github_lib_is_retried_through_the_agent_and_only_there(tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "clone" in cmd and cmd[cmd.index("--") + 1].startswith("https://"):
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: could not read Username for 'https://github.com': terminal prompts disabled\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    root = tmp_path / "p"
    (root / "libs" / "libft").mkdir(parents=True)
    with_agent = SubmoduleDownload(repo.GitClient({"PATH": "/usr/bin", "SSH_AUTH_SOCK": "/run/agent.sock"}, fake_run), HostPolicy(), ("https", "ssh"), lambda: 0.0)
    without = SubmoduleDownload(repo.GitClient({"PATH": "/usr/bin"}, fake_run), HostPolicy(), ("https", "ssh"), lambda: 0.0)

    def clones():
        return [c[c.index("--") + 1] for c in calls if "clone" in c]

    note = with_agent.fetch(root, "libs/libft", "a" * 40, "https://github.com/Rodolfo9898/libft.git", "libs/libft", 10**9)
    assert note.ok and clones() == ["https://github.com/Rodolfo9898/libft.git", "git@github.com:Rodolfo9898/libft.git"]
    calls.clear()
    with_agent.fetch(root, "libs/libft", "a" * 40, "https://gitlab.com/a/b.git", "libs/libft", 10**9)
    assert clones() == ["https://gitlab.com/a/b.git"]                                              # only github.com gets the second try
    calls.clear()
    note = without.fetch(root, "libs/libft", "a" * 40, "https://github.com/a/b.git", "libs/libft", 10**9)
    assert not note.ok and clones() == ["https://github.com/a/b.git"]                              # no agent, no second try
    cmd = next(c for c in calls if "clone" in c)
    assert "credential.helper=" in cmd and "protocol.allow=never" in cmd and "core.hooksPath=/dev/null" in cmd


def test_a_ssh_address_needs_the_agent_and_is_not_even_tried_without_it(tmp_path):
    calls = []
    root = tmp_path / "p"
    (root / "libs" / "libft").mkdir(parents=True)
    download = SubmoduleDownload(repo.GitClient({"PATH": "/usr/bin"}, lambda cmd, **kw: calls.append(cmd)), HostPolicy(), ("https", "ssh"), lambda: 0.0)
    note = download.fetch(root, "libs/libft", "a" * 40, "git@github.com:Rodolfo9898/libft.git", "libs/libft", 10**9)
    assert not note.ok and "needs your ssh-agent" in note.message and calls == []


def test_a_download_that_takes_too_long_leaves_the_folder_empty(tmp_path):
    root = tmp_path / "p"
    (root / "libs" / "libft").mkdir(parents=True)

    def slow(cmd, **kwargs):
        (root / "libs" / "libft" / "half").write_text("x")
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    download = SubmoduleDownload(repo.GitClient({"PATH": "/usr/bin"}, slow), HostPolicy(), ("https", "ssh"), lambda: 0.0)
    note = download.fetch(root, "libs/libft", "a" * 40, "https://github.com/a/b.git", "libs/libft", 10**9)
    assert not note.ok and note.message == "the download timed out" and list((root / "libs" / "libft").iterdir()) == []
