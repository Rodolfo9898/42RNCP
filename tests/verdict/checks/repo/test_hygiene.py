"""What a repository must not contain: build artifacts and secrets."""

from verdict.checks import Ctx
from verdict.checks.repo.hygiene import RepoHygiene

from tests.verdict.checks.helpers import MLX, project


def audit(repo):
    return list(RepoHygiene().run(Ctx(repo=repo.resolve(), rules=[], sandbox=None, lang="c")))


def test_a_clean_repository_passes_both_audits(tmp_path):
    artifacts, secrets = audit(project(tmp_path, "Makefile", "main.c"))
    assert (artifacts.status, secrets.status) == ("pass", "pass")
    assert artifacts.title == "Repository contains no build artifacts" and secrets.title == "Repository contains no secrets"


def test_compiled_and_system_files_are_a_warning(tmp_path):
    repo = project(tmp_path, {"main.c": "x\n", "a.o": "x\n", ".DS_Store": "x\n", "prog": "\x7fELF....", "lib.so": "x\n"})
    artifacts, secrets = audit(repo)
    assert artifacts.status == "warn" and "4 compiled/system file(s) committed" in artifacts.detail
    assert sorted(e.file for e in artifacts.evidence) == [".DS_Store", "a.o", "lib.so", "prog"] and secrets.status == "pass"


def test_credentials_are_a_failure_by_file_name_or_by_content(tmp_path):
    repo = project(tmp_path, {".env": "A=1\n", "id.pem": "x\n", "note.txt": "-----BEGIN RSA PRIVATE KEY-----\nxx\n", "tok.txt": "x\n" + "ghp_" + "a" * 36 + "\n"})
    artifacts, secrets = audit(repo)
    assert secrets.status == "fail" and "4 possible secret(s) found" in secrets.detail and artifacts.status == "pass"
    by_file = {e.file: (e.line, e.snippet) for e in secrets.evidence}
    assert by_file["note.txt"] == (1, "looks like a private key") and by_file["tok.txt"] == (2, "looks like a GitHub token")
    assert by_file[".env"][1] == "file usually holds credentials"


def test_what_minilibx_ships_is_not_the_students(tmp_path):
    artifacts, secrets = audit(project(tmp_path, MLX, {"mlx/libmlx.a": "x\n", "mlx/.env": "x\n"}))
    assert (artifacts.status, secrets.status) == ("pass", "pass")
