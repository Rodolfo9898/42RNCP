import pytest

from verdict.repository import repo


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


@pytest.mark.parametrize("rel", ["", "/", "../outside", "a/../../x", "/etc", "~", "missing", "a\\b", ".git"])
def test_an_existing_folder_must_be_a_real_folder_inside_the_root(tmp_path, rel):
    (tmp_path / "a").mkdir()
    with pytest.raises(repo.RepoError):
        repo.ProjectsFolder(tmp_path).existing(rel)


def test_an_existing_folder_may_not_be_a_symlink_leaving_the_root(tmp_path):
    outside, root = tmp_path / "outside", tmp_path / "root"
    outside.mkdir(); root.mkdir()
    (root / "escape").symlink_to(outside)
    with pytest.raises(repo.RepoError, match="symbolic link"):
        repo.ProjectsFolder(root).existing("escape")


def test_safe_path_stays_inside_the_root_and_refuses_what_leaves_it(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.c").write_text("x")
    outside = tmp_path.parent / "elsewhere"
    outside.mkdir(exist_ok=True)
    (tmp_path / "link").symlink_to(outside)
    assert repo.safe_path(tmp_path, "a/f.c") == tmp_path.resolve() / "a" / "f.c"
    assert repo.safe_path(tmp_path, "") == tmp_path.resolve()
    for bad in ("../x", "a/../../x", "link/y", "/etc/passwd"):
        with pytest.raises(repo.RepoError, match="escapes"):
            repo.safe_path(tmp_path, bad)
