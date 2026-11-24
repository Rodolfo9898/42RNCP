"""Required files named in the subject's text: folders, "at the root", example layouts."""

from verdict.checks.files.required import RequiredFilesChecker
from verdict.core.models import Rule, Source

from tests.verdict.checks.helpers import answer, project


def rule_result(repo, files, *, root=(), soft=(), notes=(), pdf="x.pdf"):
    params = {"files": [[f] for f in files], "notes": list(notes), "from_text": True,
              **({"root": list(root)} if root else {}), **({"soft": list(soft)} if soft else {})}
    rule = Rule(id="rf2", kind="required_files", title="Required files named in the subject", params=params, sources=[Source(pdf=pdf, page=5)])
    return answer(RequiredFilesChecker(), repo, rule)


def test_a_makefile_the_subject_asks_for_in_its_text_is_checked(tmp_path):
    assert rule_result(project(tmp_path / "a", "Makefile", "main.c"), ["Makefile"]).status == "pass"
    r = rule_result(project(tmp_path / "b", "main.c"), ["Makefile"])
    assert r.status == "fail" and "Missing: Makefile." in r.detail and r.title == "Required files named in the subject"


def test_a_file_the_subject_wants_at_the_root_must_be_there_not_just_somewhere(tmp_path):
    """Only in the strict projects (libft, ft_printf, get_next_line); elsewhere the layout is free (test_evaluation_rules.py)."""
    strict = "get_next_line.pdf"
    assert rule_result(project(tmp_path / "a", "signature.txt"), ["signature.txt"], root=["signature.txt"], pdf=strict).status == "pass"
    r = rule_result(project(tmp_path / "b", "docs/signature.txt"), ["signature.txt"], root=["signature.txt"], pdf=strict)
    assert r.status == "fail" and "`docs/signature.txt`" in r.detail and "belongs at the root" in r.detail      # (without root it would be a second look)
    assert rule_result(project(tmp_path / "c", "docs/signature.txt"), ["signature.txt"], pdf=strict).status == "warn"
    assert rule_result(project(tmp_path / "d", "docs/signature.txt"), ["signature.txt"], root=["signature.txt"]).status == "pass"


def test_wildcards_that_must_be_at_the_root_do_not_match_the_subfolders(tmp_path):
    get_next_line = ["get_next_line.c", "get_next_line_utils.c", "get_next_line.h"]
    gnl = "get_next_line.pdf"
    assert rule_result(project(tmp_path / "a", *get_next_line), get_next_line, root=get_next_line, pdf=gnl).status == "pass"
    nested = project(tmp_path / "b", *[f"src/{f}" for f in get_next_line])
    r = rule_result(nested, get_next_line, root=get_next_line, pdf=gnl)
    assert r.status == "fail" and "belongs at the root" in r.detail
    sources = project(tmp_path / "c", "src/a.c", "main.c")
    assert rule_result(sources, ["*.c"], root=["*.c"], pdf=gnl).status == "pass"                             # main.c is at the root
    assert rule_result(project(tmp_path / "d", "src/a.c"), ["*.c"], root=["*.c"], pdf=gnl).status == "fail"   # only in a subfolder
    assert rule_result(project(tmp_path / "e", "src/a.c"), ["*.c"], pdf=gnl).status == "pass"                 # no root rule: anywhere is fine
    assert rule_result(project(tmp_path / "f", "src/a.c"), ["*.c"], root=["*.c"]).status == "pass"            # "all at the root" is free elsewhere


def test_a_folder_the_subject_lists_has_to_be_a_folder(tmp_path):
    assert rule_result(project(tmp_path / "a", "src/main.c", "static/app.css"), ["src/", "static/"]).status == "pass"
    r = rule_result(project(tmp_path / "b", "src/main.c", "static"), ["src/", "static/"])                      # `static` is a file here
    assert r.status == "fail" and "Missing: static/." in r.detail
    elsewhere = rule_result(project(tmp_path / "c", "app/src/main.c"), ["src/"], pdf="libft.pdf")
    assert elsewhere.status == "warn" and "`app/src/`" in elsewhere.detail
    free = rule_result(project(tmp_path / "d", "app/src/main.c"), ["src/"])
    assert free.status == "pass" and "`app/src/`" in free.detail


def test_names_that_only_an_example_layout_shows_are_a_second_look_never_a_failure(tmp_path):
    r = rule_result(project(tmp_path, "Makefile"), ["Makefile", "secrets/", "srcs/docker-compose.yml"], soft=["secrets/", "srcs/docker-compose.yml"],
                    pdf="ft_printf.pdf")
    assert r.status == "warn" and "only shows these in an example layout" in r.detail and "`secrets/`" in r.detail
    assert "Missing" not in r.detail
    free = rule_result(project(tmp_path / "free", "Makefile"), ["Makefile", "secrets/"], soft=["secrets/"])
    assert free.status == "pass" and "an example is not a requirement" in free.detail
    complete = rule_result(project(tmp_path / "ok", "Makefile", "secrets/db.txt", "srcs/docker-compose.yml"), ["Makefile", "secrets/", "srcs/docker-compose.yml"],
                           soft=["secrets/", "srcs/docker-compose.yml"])
    assert complete.status == "pass"
    hard = rule_result(project(tmp_path / "bad", "secrets/db.txt"), ["Makefile", "secrets/"], soft=["secrets/"])
    assert hard.status == "fail" and "Missing: Makefile." in hard.detail                                       # what is asked outright still fails


def test_a_name_from_a_plain_ls_listing_is_only_a_hint(tmp_path):
    r = rule_result(project(tmp_path, "writeup1"), ["writeup1", "writeup2"], soft=["writeup1", "writeup2"])
    assert r.status == "pass" and "`writeup2`" in r.detail
