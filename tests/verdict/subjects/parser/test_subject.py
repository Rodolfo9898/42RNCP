from pathlib import Path

import pytest

from tests.conftest import SUBJECT_PAGES
from tests.paths import SAMPLES as LIBRARY
from verdict.subjects.pdf import read_pages
from verdict.subjects.spec import parse_subject

SAMPLES = LIBRARY / "common-core"
needs_samples = pytest.mark.skipif(not (SAMPLES / "push_swap.pdf").exists(), reason="sample subjects not present")


def kinds(spec):
    return {r.kind for r in spec.rules}


def test_parse_synthetic_subject():
    spec = parse_subject("push_swap.pdf", SUBJECT_PAGES)
    assert spec.lang == "c"
    assert {"required_files", "program", "makefile_rules", "allowed_functions", "flags", "no_relink", "language"} <= kinds(spec)
    allowed = next(r for r in spec.rules if r.kind == "allowed_functions")
    assert allowed.params["functions"] == ["read", "write", "malloc", "free", "exit", "ft_printf"]
    assert allowed.params["libft"] is True
    files = next(r for r in spec.rules if r.kind == "required_files")
    assert files.params["files"] == [["Makefile"], ["*.h"], ["*.c"]]
    # the table of contents must not produce rules
    assert not any("Introduction" in r.text for r in spec.rules)


def test_the_language_is_c_when_the_subject_says_so_cpp_when_it_asks_for_std98_and_unknown_otherwise():
    assert parse_subject("a.pdf", ["Chapter I\nRules\nYour project must be written in C.\n"]).lang == "c"
    assert parse_subject("b.pdf", ["Chapter I\nRules\nYour code must still compile with -std=c++98 and the flags.\n"]).lang == "cpp"
    assert parse_subject("c.pdf", ["Chapter I\nRules\nNothing is said about the language here at all.\n"]).lang is None


@needs_samples
def test_real_push_swap():
    spec = parse_subject("push_swap.pdf", read_pages(SAMPLES / "push_swap.pdf"))
    programs = {(r.section, r.params["program"]) for r in spec.rules if r.kind == "program"}
    assert programs == {("mandatory", "push_swap"), ("bonus", "checker")}
    assert "norm" in kinds(spec) and "flags" in kinds(spec) and "no_relink" in kinds(spec)


@needs_samples
def test_real_libft_lists_every_function():
    spec = parse_subject("libft.pdf", read_pages(SAMPLES / "libft.pdf"))
    names = next(r for r in spec.rules if r.kind == "functions_defined").params["names"]
    assert len(names) == 43 and "ft_strlen" in names and "ft_substr" in names and "ft_lstmap" in names
    allowed = next(r for r in spec.rules if r.kind == "allowed_functions")
    assert set(allowed.params["functions"]) == {"malloc", "free", "write"}


@needs_samples
def test_real_cpp_exercises_become_units():
    spec = parse_subject("cpp01.pdf", read_pages(SAMPLES / "cpp01.pdf"))
    assert spec.lang == "cpp"
    units = sorted({r.unit for r in spec.rules if r.kind == "build_unit"})
    assert units == [f"ex0{i}" for i in range(7)]


@needs_samples
@pytest.mark.parametrize("pdf", sorted(p.name for p in SAMPLES.glob("*.pdf")) if SAMPLES.is_dir() else [])
def test_every_sample_parses(pdf):
    spec = parse_subject(pdf, read_pages(SAMPLES / pdf))
    assert spec.rules, f"no rules extracted from {pdf}"
    assert len({r.id for r in spec.rules}) == len(spec.rules)


def test_the_real_ft_printf_subject_asks_for_the_root_or_a_subfolder():
    pdf = SAMPLES / "ft_printf.pdf"
    if not pdf.is_file():
        pytest.skip("the library PDF is not here")
    spec = parse_subject("ft_printf.pdf", read_pages(pdf))
    files = [r.params["files"] for r in spec.rules if r.kind == "required_files"]
    assert files == [[["Makefile"], ["*.h", "*/*.h"], ["*.c", "*/*.c"]]]


# What the text of the library's subjects asks for outside their tables, reviewed by hand against the PDFs. If the parser changes and
# this changes, read the sentences behind the difference before updating it: a new entry is either a real catch or a false positive.
EXPECTED_FROM_TEXT = {
    "common-core/born2beroot.pdf": [("signature.txt",)],
    "common-core/inception.pdf": [("Makefile", "secrets/", "srcs/", "secrets/credentials.txt", "secrets/db_password.txt", "secrets/db_root_password.txt",
                                   "srcs/docker-compose.yml", "srcs/.env", "srcs/requirements/")],
    "common-core/minitalk.pdf": [("Makefile",)], "post-common-core/lem_in.pdf": [("Makefile",)],
    "post-common-core/ft_ssl_des.pdf": [("Makefile",)], "post-common-core/ft_ssl_rsa.pdf": [("Makefile",)],        # "You must submit a Makefile."
    "rncp/abstract_data.pdf": [("Makefile",)], "rncp/boot2root.pdf": [("writeup1", "writeup2")], "rncp/ft_ality.pdf": [("Makefile",)],
    "rncp/ft_nmap.pdf": [("Makefile",)], "rncp/ft_ping.pdf": [("Makefile",)], "rncp/ft_script.pdf": [("Makefile",)],
    "rncp/ft_select.pdf": [("author",)], "rncp/ft_ssl_md5.pdf": [("Makefile",)], "rncp/ft_traceroute.pdf": [("Makefile",)],
    "rncp/gomoku.pdf": [("Makefile",)], "rncp/h42n42.pdf": [("Makefile", "Dockerfile", "docker-compose.yml", "src/", "static/")],
    "rncp/kfs3.pdf": [("Makefile",)], "rncp/leaffliction.pdf": [("signature.txt",)],
    "rncp/libftpp.pdf": [("Makefile", "libftpp.hpp", "data_structures.hpp", "design_patterns.hpp", "threading.hpp", "network.hpp", "mathematics.hpp")],
    "rncp/nm.pdf": [("Makefile",)], "rncp/strace.pdf": [("Makefile",)],
}


def test_the_library_of_subjects_gives_exactly_the_reviewed_text_requirements():
    if not (LIBRARY / "common-core").is_dir():
        pytest.skip("the library is not here")
    found = {}
    for pdf in sorted(LIBRARY.rglob("*.pdf")):
        if pdf.name == "en.norm.pdf":
            continue
        rules = [r for r in parse_subject(pdf.name, read_pages(pdf)).rules if r.kind == "required_files" and r.params.get("from_text")]
        if rules:
            found[f"{pdf.parent.name}/{pdf.name}"] = [tuple(e[0] for e in r.params["files"]) for r in rules]
    assert found == EXPECTED_FROM_TEXT


def test_the_library_gives_the_layout_and_root_details_a_human_checked():
    if not (LIBRARY / "common-core").is_dir():
        pytest.skip("the library is not here")
    def rule(path):
        return next(r for r in parse_subject(Path(path).name, read_pages(LIBRARY / path)).rules if r.kind == "required_files" and r.params.get("from_text"))
    assert rule("common-core/born2beroot.pdf").params["root"] == ["signature.txt"]
    assert rule("rncp/ft_select.pdf").params["root"] == ["author"] and rule("rncp/leaffliction.pdf").params["root"] == ["signature.txt"]
    inception = rule("common-core/inception.pdf").params
    assert inception["root"] == ["Makefile"] and "Makefile" not in inception["soft"] and "srcs/" in inception["soft"]       # the layout is an example
    assert rule("rncp/boot2root.pdf").params["soft"] == ["writeup1", "writeup2"]
    h42 = rule("rncp/h42n42.pdf")
    assert h42.section == "mandatory" and ".gitignore" not in [e[0] for e in h42.params["files"]]                          # (it is "optional but recommended")
    gnl = next(r for r in parse_subject("get_next_line.pdf", read_pages(LIBRARY / "common-core" / "get_next_line.pdf")).rules if r.kind == "required_files")
    assert gnl.params["root"] == ["get_next_line.c", "get_next_line_utils.c", "get_next_line.h"]
    assert not [r for r in parse_subject("libft.pdf", read_pages(LIBRARY / "common-core" / "libft.pdf")).rules if r.params.get("from_text")]   # a table already says it
