import pytest

from verdict.repository import repo
from verdict.repository.repo.address.urls import SCP_RE, SSH_RE


@pytest.mark.parametrize("url", [
    "git@github.com:user/repo.git",
    "git@github.com:user/repo",
    "git@vogsphere.42lisboa.com:vogsphere/intra-uuid-1234-abcd-56789",
    "ssh://git@github.com/user/repo.git",
    "ssh://git@gitlab.example.org:2222/group/sub-group/repo.git",
])
def test_ssh_urls_are_accepted(url):
    assert repo.validate_url(f"  {url}  ") == url


@pytest.mark.parametrize("url", [
    "https://github.com/user/repo.git", "http://github.com/user/repo", "file:///etc/passwd", "/etc/passwd", "../repo", "ext::sh -c touch% /tmp/x",
    "git@github.com:user/../repo.git", "-oProxyCommand=x@host:repo", "git@-host:user/repo", "", "github.com/user/repo",
])
def test_everything_but_an_ssh_address_is_refused(url):
    with pytest.raises(repo.RepoError, match="Only SSH"):
        repo.validate_url(url)


def test_the_two_accepted_forms_do_not_overlap():
    assert SCP_RE.match("git@github.com:user/repo.git") and not SSH_RE.match("git@github.com:user/repo.git")
    assert SSH_RE.match("ssh://git@github.com/user/repo.git") and not SCP_RE.match("ssh://git@github.com/user/repo.git")


@pytest.mark.parametrize("url,expected", [
    ("git@github.com:user/repo.git", ("git", "github.com", None)),
    ("ssh://git@gitlab.example.org:2222/group/repo.git", ("git", "gitlab.example.org", 2222)),
    ("ssh://me@host/repo", ("me", "host", None)),
    ("me@vogsphere.42lisboa.com:vogsphere/intra-uuid-1234", ("me", "vogsphere.42lisboa.com", None)),
])
def test_user_host_and_port_come_out_of_an_address(url, expected):
    assert repo.ssh_target(repo.validate_url(url)) == expected
