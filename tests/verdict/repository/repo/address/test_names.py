import pytest

from verdict.repository import repo


@pytest.mark.parametrize("url,expected", [
    ("git@github.com:user/push_swap.git", "push_swap"),
    ("ssh://git@host:22/group/my-repo", "my-repo"),
    ("git@vogsphere.42lisboa.com:vogsphere/intra-uuid-1234", "intra-uuid-1234"),
    ("git@github.com:user/-weird.git", "project"),
    ("git@github.com:user/", "user"),
])
def test_default_name(url, expected):
    assert repo.default_name(url) == expected


@pytest.mark.parametrize("name,ok", [("libft", True), ("a.b-c_d", True), ("x" * 100, True), ("x" * 101, False), ("-rf", False), ("..", False),
                                     ("a/b", False), ("a b", False), ("", False)])
def test_what_a_project_may_be_called(name, ok):
    assert bool(repo.NAME_RE.match(name)) is ok
