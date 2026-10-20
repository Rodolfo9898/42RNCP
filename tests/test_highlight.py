import time

import pytest

from verdict import highlight


def classes(result, line):
    return [(cls, text) for cls, text in result["lines"][line]]


def test_c_source_is_tokenized_line_by_line():
    src = '#include <stdio.h>\n\nint\tmain(void)\n{\n\treturn (0); // done\n}\n'
    out = highlight.tokenize("main.c", src)
    assert out["language"] == "C"
    assert len(out["lines"]) == src.count("\n") + 1
    assert out["lines"][0][0][0] == "pp"            # #include
    assert ("ty", "int") in classes(out, 2)
    assert ("c", "// done") in classes(out, 4)
    assert ("n", "0") in classes(out, 4)
    assert out["lines"][1] == []                      # blank line


@pytest.mark.parametrize("filename,text,language", [
    ("Makefile", "all:\n\tcc main.c\n", "Makefile"),
    ("Dockerfile", "FROM debian\nRUN make\n", "Docker"),
    ("a.cpp", "class A {};\n", "C++"),
    ("a.hpp", "class A {};\n", "C++"),
    ("a.tpp", "template <class T> T f();\n", "C++"),
    ("a.py", "def f():\n    return 1\n", "Python"),
    ("a.sh", "#!/bin/sh\necho hi\n", "Bash"),
    ("a.js", "const a = 1;\n", "JavaScript"),
    ("a.ts", "let a: number = 1;\n", "TypeScript"),
    ("a.json", '{"a": 1}\n', "JSON"),
    ("a.yml", "a: 1\nb:\n  - c\n", "YAML"),
    ("a.html", "<p class='x'>hi</p>\n", "HTML"),
    ("a.css", "a { color: red; }\n", "CSS"),
    ("a.md", "# Title\n\ntext\n", "Markdown"),
    ("a.rs", "fn main() {}\n", "Rust"),
    ("a.go", "package main\n", "Go"),
    ("a.java", "class A {}\n", "Java"),
    ("a.sql", "SELECT 1;\n", "SQL"),
    ("a.php", "<?php echo 1;\n", "PHP"),
])
def test_languages_a_42_repo_may_contain(filename, text, language):
    out = highlight.tokenize(filename, text)
    assert out is not None, filename
    assert language.lower() in out["language"].lower()
    assert any(cls for line in out["lines"] for cls, _ in line), "nothing was classified"


def test_text_is_reassembled_exactly():
    src = "int a;\r\nint b;\n\n\tx = \"a\\nb\";\n"
    out = highlight.tokenize("a.c", src)
    assert ["".join(t for _, t in line) for line in out["lines"]] == src.replace("\r\n", "\n").split("\n")


@pytest.mark.parametrize("filename,text", [
    ("notes.txt", "just text\n"),
    ("data.cub", "111\n1 0 1\n"),
    ("unknown.zzzz", "whatever\n"),
])
def test_unhighlightable_files_return_none(filename, text):
    assert highlight.tokenize(filename, text) is None


def test_limits_protect_against_huge_inputs():
    assert highlight.tokenize("a.c", "int a;\n" * 40_000) is None          # over the size cap
    assert highlight.tokenize("a.js", "var a = '" + "x" * 5_000 + "';\n") is None  # minified-style long line


def test_html_in_source_stays_text():
    out = highlight.tokenize("a.c", 'puts("<img src=x onerror=alert(1)>");\n')
    flat = "".join(t for line in out["lines"] for _, t in line)
    assert "<img src=x onerror=alert(1)>" in flat    # kept verbatim as data; the UI uses textContent


def test_subprocess_wrapper_matches_direct_call():
    direct = highlight.tokenize("a.c", "int a;\n")
    assert highlight.highlight("a.c", "int a;\n") == direct


def test_subprocess_wrapper_gives_up_instead_of_hanging(monkeypatch):
    monkeypatch.setattr(highlight, "TIMEOUT", 0.001)
    start = time.monotonic()
    assert highlight.highlight("a.c", "int a;\n") is None
    assert time.monotonic() - start < 3


ELIOM = """\
[%%shared
  open Eliom_content.Html.D
]
let%server main = Eliom_service.create ()
let%client alert s = Js.string s
let%shared f x = [%client ~%x + 1]
{client{ let old_style = 42 }}
(* [%client in a comment *)
"""


def _classes(result):
    return {text: cls for line in result["lines"] for cls, text in line}


def test_eliom_files_are_highlighted_as_eliom():
    for name in ("page.eliom", "page.eliomi"):
        result = highlight.tokenize(name, ELIOM)
        assert result is not None and result["language"] == "Eliom"


def test_eliom_extensions_are_marked_and_ocaml_still_works():
    result = highlight.tokenize("page.eliom", ELIOM)
    by_text = _classes(result)
    assert by_text["[%%"] == "pp" and by_text["shared"] == "k"
    assert by_text["%"] == "pp" and by_text["client"] == "k"
    assert by_text["~%x"] == "pp"
    assert by_text["{client{"] == "pp"
    assert by_text["open"] == "k"                       # plain OCaml is untouched
    assert "\n".join("".join(t for _, t in line) for line in result["lines"]) == ELIOM
    assert by_text["(* [%client in a comment *)"] == "c"    # comments win over the extensions
