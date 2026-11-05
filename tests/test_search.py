"""The Search view's backend: find text in the files of the reviewed project."""

import os
import time
from pathlib import Path

import pytest

from verdict import search
from verdict.search import glob_regex, search as run_search, search_safely

from .test_api import attach_repo, client  # noqa: F401  (the app fixture)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "p"
    (root / "src" / "utils").mkdir(parents=True)
    (root / "libs" / "libft").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n\tbare = false\n")
    (root / "Makefile").write_text("NAME = fractol\nall: $(NAME)\n")
    (root / "src" / "main.c").write_text('#include "fractol.h"\n\nint\tmain(void)\n{\n\treturn (Fractol(0));\n}\n')
    (root / "src" / "utils" / "split.c").write_text("char **ft_split(char const *s, char c)\n{\n\treturn (NULL);\n}\n")
    (root / "libs" / "libft" / "ft_split.c").write_text("// the other ft_split\n")
    (root / "image.bin").write_bytes(b"\x00\x01fractol\x00")
    (root / "link.c").symlink_to(root / "src" / "main.c")
    return root


def found(result):
    return {f["path"]: [(m["line"], m["col"], m["length"]) for m in f["matches"]] for f in result["files"]}


def test_a_literal_search_finds_every_occurrence_with_its_line_and_column(project):
    result = run_search(project, "fractol", case=True)
    assert found(result) == {"Makefile": [(1, 7, 7)], "src/main.c": [(1, 10, 7)]} and result["total"] == 2 and not result["truncated"]
    assert result["files"][1]["matches"][0]["preview"] == '#include "fractol.h"'


def test_the_case_is_ignored_unless_asked(project):
    assert found(run_search(project, "FRACTOL"))["src/main.c"] == [(1, 10, 7), (5, 9, 7)]            # also Fractol( in main
    assert found(run_search(project, "FRACTOL", case=True)) == {}
    assert found(run_search(project, "Fractol", case=True)) == {"src/main.c": [(5, 9, 7)]}


def test_whole_word_does_not_match_inside_a_longer_word(project):
    assert found(run_search(project, "main", word=True)) == {"src/main.c": [(3, 4, 4)]}
    assert "src/main.c" in found(run_search(project, "main"))
    assert found(run_search(project, "split")) != {} and found(run_search(project, "split", word=True)) == {}      # ft_split is one word


def test_a_regular_expression_when_asked_and_text_when_not(project):
    assert found(run_search(project, r"ft_\w+", regex=True))["src/utils/split.c"] == [(1, 7, 8)]
    assert found(run_search(project, "(Fractol", case=True)) == {"src/main.c": [(5, 8, 8)]}              # not a regex: the parenthesis is text
    assert found(run_search(project, "return (", case=True))["src/main.c"] == [(5, 1, 8)]
    with pytest.raises(ValueError, match="not a valid regular expression"):
        run_search(project, "(", regex=True)
    assert all(m["length"] > 0 for f in run_search(project, "x*", regex=True)["files"] for m in f["matches"])


def test_include_and_exclude_globs_work_like_vs_codes(project):
    assert set(found(run_search(project, "split"))) == {"src/utils/split.c", "libs/libft/ft_split.c"}
    assert set(found(run_search(project, "ft_split", include="*.c"))) == {"src/utils/split.c", "libs/libft/ft_split.c"}
    assert set(found(run_search(project, "ft_split", include="src/**"))) == {"src/utils/split.c"}
    assert set(found(run_search(project, "ft_split", exclude="libs"))) == {"src/utils/split.c"}
    assert set(found(run_search(project, "ft_split", exclude="libs/, nothing"))) == {"src/utils/split.c"}
    assert set(found(run_search(project, "fractol", include="*.{c,h}", case=True))) == {"src/main.c"}
    assert found(run_search(project, "fractol", include="*.py")) == {}


@pytest.mark.parametrize("pattern,path,expected", [
    ("*.c", "a.c", True), ("*.c", "src/a.c", True), ("*.c", "a.h", False), ("src", "src/a.c", True), ("src/", "src/a.c", True),
    ("src/*.c", "src/a.c", True), ("src/*.c", "src/x/a.c", False), ("src/**", "src/x/a.c", True), ("*.{c,h}", "src/a.h", True),
    ("*.{c,h}", "a.o", False), ("**/test*", "libs/test_a.c", True), ("./Makefile", "Makefile", True), ("a?.c", "ab.c", True), ("a?.c", "a/.c", False),
    ("src/a.c", "other/src/a.c", False), ("a.c", "src/a.c", True),
])
def test_globs(pattern, path, expected):
    assert bool(glob_regex(pattern).fullmatch(path)) is expected


def test_binary_files_links_and_git_are_never_searched(project):
    assert "image.bin" not in found(run_search(project, "fractol")) and "link.c" not in found(run_search(project, "fractol"))
    assert not any(p.startswith(".git") for p in found(run_search(project, "bare")))


def test_the_results_are_bounded(project, monkeypatch):
    big = project / "big.txt"
    big.write_text("needle\n" * 500)
    monkeypatch.setattr(search, "MAX_PER_FILE", 50)
    result = run_search(project, "needle")
    assert result["total"] == 50 and result["truncated"] and len(result["files"][0]["matches"]) == 50
    monkeypatch.setattr(search, "MAX_PER_FILE", 200)
    monkeypatch.setattr(search, "MAX_MATCHES", 120)
    (project / "big2.txt").write_text("needle\n" * 500)
    result = run_search(project, "needle")
    assert result["total"] == 120 and result["truncated"]


def test_a_long_line_is_cut_around_the_match(project):
    (project / "long.txt").write_text("x" * 1000 + "needle" + "y" * 1000 + "\n")
    match = found(run_search(project, "needle", include="long.txt"))["long.txt"][0]
    assert match == (1, 1000, 6)
    item = run_search(project, "needle", include="long.txt")["files"][0]["matches"][0]
    assert len(item["preview"]) <= search.PREVIEW and "needle" in item["preview"] and item["preview_start"] == 940


def test_nonsense_queries_are_refused_with_a_reason(project):
    for query in ("", "x" * 201):
        assert "between 1 and 200" in search_safely(project, query)["error"]
    assert "not a valid regular expression" in search_safely(project, "(", regex=True)["error"]
    assert search_safely(project, "fractol", regex=True)["total"] == 3                                    # (Makefile, and main.c twice: Fractol( counts)


def test_a_pattern_that_backtracks_for_ever_is_stopped_and_the_server_keeps_answering(project):
    (project / "evil.txt").write_text("a" * 40 + "!\n")
    start = time.monotonic()
    result = search_safely(project, r"(a+)+$", regex=True, seconds=1.5)
    assert time.monotonic() - start < 6 and "took too long" in result["error"] and result["files"] == []
    assert search_safely(project, "fractol")["total"] == 3                                              # the next search is not affected


def test_the_regex_child_gets_nothing_from_this_process(project, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    seen = {}
    real = search.subprocess.run

    def spy(cmd, **kw):
        seen.update(cmd=cmd, env=kw["env"])
        return real(cmd, **kw)

    monkeypatch.setattr(search.subprocess, "run", spy)
    search_safely(project, "fractol", regex=True)
    assert "-I" in seen["cmd"] and set(seen["env"]) <= {"PATH", "PYTHONDONTWRITEBYTECODE"}


# ---------------------------------------------------------------- the endpoint


def test_the_endpoint_searches_the_project_of_the_session(client):
    c, main = client
    sid = c.post("/api/sessions").json()["id"]
    assert c.get(f"/api/sessions/{sid}/search", params={"q": "x"}).status_code == 404                  # no repository yet
    repo = attach_repo(main, sid, "se1")
    (repo / "a.c").write_text("int Needle;\nint needle;\n")
    answer = c.get(f"/api/sessions/{sid}/search", params={"q": "needle"}).json()
    assert [(f["path"], [m["line"] for m in f["matches"]]) for f in answer["files"]] == [("a.c", [1, 2])]
    assert c.get(f"/api/sessions/{sid}/search", params={"q": "needle", "case": "true"}).json()["total"] == 1
    assert c.get(f"/api/sessions/{sid}/search", params={"q": "ne+dle", "regex": "true", "word": "true"}).json()["total"] == 2
    assert c.get(f"/api/sessions/{sid}/search", params={"q": "needle", "include": "*.h"}).json()["total"] == 0
    assert c.get(f"/api/sessions/{sid}/search", params={"q": ""}).json()["error"]
    assert c.get("/api/sessions/nope/search", params={"q": "x"}).status_code == 404


def test_commas_inside_braces_belong_to_the_pattern():
    assert search.split_globs("*.c, *.{c,h}, src/{a,b}/**,") == ["*.c", " *.{c,h}", " src/{a,b}/**"]
    assert search.split_globs("") == [] and search.split_globs(" , ") == []


def test_one_line_with_hundreds_of_matches_does_not_flood_the_results(project):
    (project / "same.txt").write_text("ab" * 300 + "\nab\n")
    matches = run_search(project, "ab", include="same.txt")["files"][0]["matches"]
    assert [m["line"] for m in matches].count(1) == search.MAX_PER_LINE and [m["line"] for m in matches].count(2) == 1


def test_a_cap_in_the_middle_of_a_line_still_stops_at_the_cap(project, monkeypatch):
    monkeypatch.setattr(search, "MAX_PER_FILE", 7)
    (project / "same.txt").write_text("ab" * 30 + "\n")
    result = run_search(project, "ab", include="same.txt")
    assert result["total"] == 7 and result["truncated"]
