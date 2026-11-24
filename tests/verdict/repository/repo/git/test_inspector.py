import subprocess

from verdict.repository import repo
from verdict.repository.repo.git.inspector import FolderInspector


def make_repository(folder, remote="git@github.com:me/libft.git"):
    folder.mkdir(parents=True)
    git = ["git", "-C", str(folder)]
    subprocess.run([*git, "init", "-q"], check=True)
    if remote:
        subprocess.run([*git, "remote", "add", "origin", remote], check=True)
    (folder / "a.c").write_text("int a;\n")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "-c", "user.name=Me", "-c", "user.email=m@e", "commit", "-qm", "first"], check=True)


def test_a_repository_tells_its_remote_and_its_last_commit(tmp_path):
    make_repository(tmp_path / "libft")
    info = FolderInspector(repo.GitClient.offline()).info(tmp_path / "libft")
    assert (info.url, info.subject, info.author) == ("git@github.com:me/libft.git", "first", "Me") and info.commit


def test_a_folder_without_git_has_nothing_to_tell(tmp_path):
    (tmp_path / "plain").mkdir()
    assert FolderInspector(repo.GitClient.offline()).info(tmp_path / "plain") == repo.RepoInfo(url="", commit="", subject="", author="")


def test_a_repository_without_a_remote_still_has_a_commit(tmp_path):
    make_repository(tmp_path / "local", remote="")
    info = FolderInspector(repo.GitClient.offline()).info(tmp_path / "local")
    assert info.url == "" and info.subject == "first"


def test_the_last_commit_comes_with_the_address_it_was_cloned_from(tmp_path):
    make_repository(tmp_path / "libft")
    info = FolderInspector(repo.GitClient.offline()).last_commit(tmp_path / "libft", "git@github.com:me/other.git")
    assert info.url == "git@github.com:me/other.git" and info.subject == "first"


def test_git_that_cannot_be_run_gives_empty_fields_not_an_error(tmp_path):
    def broken(cmd, **kwargs):
        raise FileNotFoundError("git")

    (tmp_path / ".git").mkdir()
    assert FolderInspector(repo.GitClient.offline(broken)).info(tmp_path) == repo.RepoInfo(url="", commit="", subject="", author="")
