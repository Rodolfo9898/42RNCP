import pytest

from verdict.repository import repo
from verdict.repository.repo.folders.listing import DestinationFolders, ReviewableFolders

from tests.verdict.repository.repo.git.test_inspector import make_repository


def test_list_folders_suggests_only_plain_folders(tmp_path):
    (tmp_path / "42" / "common-core").mkdir(parents=True)
    (tmp_path / "42" / "common-core" / "deep" / "deeper").mkdir(parents=True)
    (tmp_path / "libft" / ".git").mkdir(parents=True)
    assert repo.list_folders(tmp_path) == ["42", "42/common-core"]  # two levels deep, no repos


def test_the_depth_of_a_listing_can_be_asked_for(tmp_path):
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    assert DestinationFolders(1).walk(tmp_path) == ["a"] and repo.list_folders(tmp_path, depth=3) == ["a", "a/b", "a/b/c"]


def test_list_folders_skips_hidden_folders_links_and_files(tmp_path):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file").write_text("x")
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    assert repo.list_folders(tmp_path) == ["real"]


def test_list_existing_marks_repositories_and_does_not_search_inside_them(tmp_path):
    (tmp_path / "libft" / ".git").mkdir(parents=True)
    (tmp_path / "libft" / "src").mkdir()
    (tmp_path / "42" / "push_swap").mkdir(parents=True)
    (tmp_path / ".hidden").mkdir()
    assert repo.list_existing(tmp_path) == [
        {"path": "42", "git": False}, {"path": "42/push_swap", "git": False}, {"path": "libft", "git": True}]


def test_list_existing_only_offers_folders_with_a_name_a_project_may_have(tmp_path):
    (tmp_path / "ok").mkdir()
    (tmp_path / "has space").mkdir()
    (tmp_path / "-dash").mkdir()
    assert [e["path"] for e in repo.list_existing(tmp_path)] == ["ok"]
    assert ReviewableFolders(1).walk(tmp_path) == [{"path": "ok", "git": False}]


def test_a_missing_root_lists_nothing(tmp_path):
    assert repo.list_folders(tmp_path / "nowhere") == [] and repo.list_existing(tmp_path / "nowhere") == []


def test_use_existing_accepts_a_folder_and_reads_its_git_state(tmp_path):
    folder = tmp_path / "42" / "libft"
    make_repository(folder)
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


def test_tracked_files_lists_regular_files_without_git_or_links(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.c").write_text("x")
    (tmp_path / "a.c").write_text("x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    (tmp_path / "link.c").symlink_to(tmp_path / "a.c")
    assert [p.as_posix() for p in repo.tracked_files(tmp_path)] == ["a.c", "src/b.c"]
