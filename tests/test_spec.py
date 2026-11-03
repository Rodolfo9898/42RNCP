from pathlib import Path

import pytest

from verdict.pdfread import read_pages
from verdict.spec import expand_files, merge_rules, parse_norm, parse_subject

from .conftest import NORM_PAGES, SUBJECT_PAGES

LIBRARY = Path(__file__).resolve().parent.parent / "samples"
SAMPLES = LIBRARY / "common-core"


def kinds(spec):
    return {r.kind for r in spec.rules}


def test_expand_files_alternatives_and_notes():
    required, notes = expand_files("Makefile, *.h, *.{h, hpp}, ft_*.c, all at the root of the repository")
    assert required == [["Makefile"], ["*.h"], ["*.h", "*.hpp"], ["ft_*.c"]]
    assert notes == ["all at the root of the repository"]


def test_expand_files_previous_exercise_prefix():
    required, notes = expand_files("Files from the previous exercise + ScavTrap.{h, hpp}, ScavTrap.cpp")
    assert ["ScavTrap.h", "ScavTrap.hpp"] in required and ["ScavTrap.cpp"] in required
    assert "Files from the previous exercise" in notes


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


def test_manual_rules_are_not_merged_together():
    spec = parse_subject("x.pdf", ["Chapter I\nRules\nYou must do the first thing properly.\nYou must also do the second thing.\n"])
    manual = [r for r in spec.rules if r.kind == "manual"]
    assert len(manual) == 2


def test_merge_remembers_all_sources():
    a = parse_subject("a.pdf", SUBJECT_PAGES)
    b = parse_subject("b.pdf", SUBJECT_PAGES)
    merged = merge_rules(a.rules + b.rules)
    assert len(merged) == len(a.rules)
    assert {s.pdf for s in merged[0].sources} == {"a.pdf", "b.pdf"}


def test_bonus_section_is_tagged():
    pages = ["Chapter I\nMandatory part\nProgram Name\nfoo\nDescription\nx\n",
             "Chapter II\nBonus part\nProgram Name\nbar\nFiles to Submit\n*.c\nDescription\ny\n"]
    spec = parse_subject("x.pdf", pages)
    sections = {r.params["program"]: r.section for r in spec.rules if r.kind == "program"}
    assert sections == {"foo": "mandatory", "bar": "bonus"}


def test_norm_keeps_only_what_norminette_cannot_check():
    spec = parse_norm("en.norm.pdf", NORM_PAGES)
    assert spec.lang == "c"
    assert [r.kind for r in spec.rules].count("norm") == 1
    manual = [r.text for r in spec.rules if r.kind == "manual"]
    assert manual == ["Your comments should be in English, and useful.", "Inclusion of unused headers is forbidden."]
    assert all(r.sources[0].pdf == "en.norm.pdf" for r in spec.rules)


def test_norm_rule_merges_with_the_subjects_own():
    norm = next(r for r in parse_norm("en.norm.pdf", NORM_PAGES).rules if r.kind == "norm")
    own = next(r for r in parse_subject("push_swap.pdf", SUBJECT_PAGES).rules if r.kind == "norm")
    merged = merge_rules([own, norm])
    assert len(merged) == 1 and {s.pdf for s in merged[0].sources} == {"push_swap.pdf", "en.norm.pdf"}


@pytest.mark.skipif(not (LIBRARY / "en.norm.pdf").exists(), reason="the Norm is not present")
def test_real_norm_lists_the_starred_rules():
    spec = parse_norm("en.norm.pdf", read_pages(LIBRARY / "en.norm.pdf"))
    manual = [r.text for r in spec.rules if r.kind == "manual"]
    assert len(manual) == 9
    assert any("unused headers" in t for t in manual) and any("42 header" in t for t in manual)


needs_samples = pytest.mark.skipif(not (SAMPLES / "push_swap.pdf").exists(), reason="sample subjects not present")


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


def test_a_name_and_its_subfolder_twin_are_one_requirement_the_root_or_a_subfolder():
    # ft_printf: "Makefile, *.h, */*.h, *.c, */*.c" means headers and sources at the root OR one folder down, not both
    assert expand_files("Makefile, *.h, */*.h, *.c, */*.c")[0] == [["Makefile"], ["*.h", "*/*.h"], ["*.c", "*/*.c"]]
    assert expand_files("*/*.c, *.c")[0] == [["*.c", "*/*.c"]]                                  # whichever is listed first
    assert expand_files("*.{h, hpp}, */*.{h, hpp}")[0] == [["*.h", "*.hpp", "*/*.h", "*/*.hpp"]]
    assert expand_files("*/*.c")[0] == [["*/*.c"]]                                              # alone, nothing to fold into
    assert expand_files("src/*.c, *.c")[0] == [["src/*.c"], ["*.c"]]                            # an explicit folder is not a twin
    assert expand_files("Makefile, libft.h, ft_*.c")[0] == [["Makefile"], ["libft.h"], ["ft_*.c"]]


def test_the_real_ft_printf_subject_asks_for_the_root_or_a_subfolder():
    from pathlib import Path

    from verdict.pdfread import read_pages
    pdf = Path(__file__).resolve().parent.parent / "samples" / "common-core" / "ft_printf.pdf"
    if not pdf.is_file():
        pytest.skip("the library PDF is not here")
    spec = parse_subject("ft_printf.pdf", read_pages(pdf))
    files = [r.params["files"] for r in spec.rules if r.kind == "required_files"]
    assert files == [[["Makefile"], ["*.h", "*/*.h"], ["*.c", "*/*.c"]]]


# ---------------------------------------------------------------- required files the subject names in its text, not in a table

from verdict.spec import _sentence_files


@pytest.mark.parametrize("sentence,names,root", [
    ("You must submit a Makefile.", ["Makefile"], False),
    ("You must code in C and turn in a Makefile.", ["Makefile"], False),
    ("You must code in C and use a Makefile.", ["Makefile"], False),
    ("You must code in C and make a Makefile (respecting the usual rules)", ["Makefile"], False),
    ("You have to provide a Makefile which must produce your program.", ["Makefile"], False),
    ("Your project must include a Makefile with at least the following rules: all, clean, fclean, re.", ["Makefile"], False),
    ("Your must turn in your code, a Makefile and a basic virtual image for your kernel.", ["Makefile"], False),
    ("A Makefile is also required and must be located at the root of your directory.", ["Makefile"], True),
    ("You only have to submit a signature.txt file at the root of your repository.", ["signature.txt"], True),
    ("signature.txt must be present in your repository.", ["signature.txt"], False),
    ("You'll have to submit a file called author containing your username followed by a newline.", ["author"], False),
    ("You must provide a unified header file named libftpp.hpp, which includes all the necessary headers.", ["libftpp.hpp"], False),
    ("You are expected to provide a data_structures.hpp file, which will include all the necessary headers.", ["data_structures.hpp"], False),
])
def test_a_sentence_that_obliges_the_student_to_hand_in_a_named_file_is_a_required_file(sentence, names, root):
    assert _sentence_files(sentence) == (names, root)


@pytest.mark.parametrize("sentence", [
    "If the subject requires it, you must submit a Makefile that compiles your source files.",                  # a condition
    "If you are using OCaml, you must turn-in a Makefile able to compile your code with ocamlopt and ocamlc.",
    "A Makefile or something similar must compile the project and must contain the usual rules.",                 # not strictly a Makefile
    "A Makefile or a similar build system is required.",
    "Your Makefile must compile the project and must contain the usual rules.",                                   # about what is in it, not that it exists
    "To submit bonuses for your project, you must include a bonus rule in your Makefile.",
    "You must not submit a Makefile for the bonus.",                                                              # forbidden
    "For example, you can provide a notes.txt file with your remarks.",                                           # an example, and not an obligation
    "You must include libft.h in your headers.",                                                                  # an #include, not a file to hand in
    "A README.md file must be provided at the root of your Git repository.",                                     # the README has its own check
    "Also submit your libft folder including its own Makefile at the root of your repository.",                  # no obligation word, and libft's
    "The Dockerfiles must be called in your docker-compose.yml by your Makefile.",
    "You should submit a notes.txt file if you want to explain your choices.",                                    # conditional
    "Students may submit a checker.txt file with their own tests.",                                               # permission, not an obligation
    "The evaluator will read the signature.txt file you provide.",                                                # a statement, not an obligation
])
def test_conditions_examples_options_and_prose_about_content_are_not_required_files(sentence):
    assert _sentence_files(sentence) == ([], False)


def text_rules(pages, name="x.pdf"):
    return [r for r in parse_subject(name, pages).rules if r.kind == "required_files" and r.params.get("from_text")]


def test_a_list_of_mandatory_files_is_read_but_not_the_optional_one_and_it_belongs_to_the_whole_project_not_the_bonus():
    pages = ["Chapter VII\nBonus part\nSome bonus feature.\n",
             "Chapter VIII\nDeliverables\nYour repository must contain all the necessary files. The following files are mandatory:\nVIII.1\nRequired Files\n"
             "• README.md: Documentation of the project\n• Dockerfile: Your Docker configuration\n• docker-compose.yml: Compose configuration\n"
             "• Makefile: Build automation\n• src/: Directory containing your sources\n• Configuration files: .conf.in files\n"
             "VIII.2\nOptional but Recommended\n• .gitignore: To exclude build artifacts\n• CHANGELOG.md: Notes for the next version\n• tests/: Your own tests\n"]
    [rule] = text_rules(pages)
    assert [e[0] for e in rule.params["files"]] == ["Dockerfile", "docker-compose.yml", "Makefile", "src/"]      # no README, no "Configuration", no optional ones
    assert "CHANGELOG.md" not in str(rule.params) and "tests/" not in str(rule.params)                          # (optional entries with ordinary names too)
    assert rule.section == "mandatory"                                                                          # (the previous chapter was the bonus)


def test_a_listing_of_the_expected_layout_is_a_hint_and_a_sentence_that_asks_for_a_file_outright_stays_a_requirement():
    pages = ["Chapter III\nGeneral guidelines\nA Makefile is also required and must be located at the root of your directory.\n",
             "Below is an example of the expected directory structure:\n$> ls -alR\ntotal XX\n"
             "drwxrwxr-x 3 wil wil 4096 avril 42 20:42 .\ndrwxrwxrwt 17 wil wil 4096 avril 42 20:42 ..\n"
             "-rw-rw-r-- 1 wil wil XXXX avril 42 20:42 Makefile\ndrwxrwxr-x 3 wil wil 4096 avril 42 20:42 srcs\n"
             "./srcs:\ntotal XX\ndrwxrwxr-x 3 wil wil 4096 avril 42 20:42 .\n-rw-rw-r-- 1 wil wil XXXX avril 42 20:42 docker-compose.yml\n"
             "drwxrwxr-x 5 wil wil 4096 avril 42 20:42 requirements\n./srcs/requirements:\ntotal XX\n"
             "drwxrwxr-x 5 wil wil 4096 avril 42 20:42 nginx\n"]
    [rule] = text_rules(pages)
    assert [e[0] for e in rule.params["files"]] == ["Makefile", "srcs/", "srcs/docker-compose.yml", "srcs/requirements/"]   # nothing deeper than two levels
    assert rule.params["root"] == ["Makefile"] and rule.params["soft"] == ["srcs/", "srcs/docker-compose.yml", "srcs/requirements/"]


def test_a_plain_ls_names_files_softly_and_bracketed_names_are_optional():
    pages = ["Chapter VII\nSubmission\n• Your repository layout must include:\n$> ls\nwriteup1\nwriteup2\n[scripts/]\n[bonus/]\nThe scripts/ folder is optional.\n"]
    [rule] = text_rules(pages)
    assert [e[0] for e in rule.params["files"]] == ["writeup1", "writeup2"] and rule.params["soft"] == ["writeup1", "writeup2"]


def test_a_listing_that_is_not_about_the_layout_is_ignored():
    pages = ["Chapter V\nMandatory part\nRun it like this and read the output:\n$> ls\nfoo\nbar\n"]
    assert text_rules(pages) == []


def test_the_turn_in_chapter_is_read_for_files_even_though_it_is_skipped_for_everything_else_and_belongs_to_the_mandatory_part():
    pages = ["Chapter V\nBonus part\nA bonus feature.\n", "Chapter VI\nSubmission and peer-evaluation\nYou must turn in your code, a Makefile and a basic virtual image.\n"]
    [rule] = text_rules(pages)
    assert [e[0] for e in rule.params["files"]] == ["Makefile"] and rule.section == "mandatory"
    assert not [r for r in parse_subject("x.pdf", pages).rules if r.kind == "manual"]                      # it does not become a vague manual item


def test_what_a_table_already_requires_is_not_asked_twice_and_the_sentence_is_not_left_as_a_manual_item():
    pages = ["Chapter V\nMandatory part\nProgram Name\nlibftprintf.a\nTurn in files\nMakefile, *.h, *.c\nDescription\n"
             "You must submit a Makefile that compiles your source files.\n"]
    spec = parse_subject("x.pdf", pages)
    assert [r.params["files"] for r in spec.rules if r.kind == "required_files"] == [[["Makefile"], ["*.h"], ["*.c"]]]
    assert not [r for r in spec.rules if r.kind == "manual" and "Makefile" in r.text]


def test_a_table_note_saying_at_the_root_is_a_requirement_for_those_files():
    required, notes = expand_files("get_next_line.c, get_next_line.h, all at the root of the repository")
    from verdict.spec import _file_params
    assert _file_params(required, notes)["root"] == ["get_next_line.c", "get_next_line.h"]
    assert "root" not in _file_params(*expand_files("Makefile, *.h, *.c"))


REAL = Path(__file__).resolve().parent.parent / "samples"

# What the text of the library's subjects asks for outside their tables, reviewed by hand against the PDFs. If the parser changes and
# this changes, read the sentences behind the difference before updating it: a new entry is either a real catch or a false positive.
EXPECTED_FROM_TEXT = {
    "common-core/born2beroot.pdf": [("signature.txt",)],
    "common-core/inception.pdf": [("Makefile", "secrets/", "srcs/", "secrets/credentials.txt", "secrets/db_password.txt", "secrets/db_root_password.txt",
                                   "srcs/docker-compose.yml", "srcs/.env", "srcs/requirements/")],
    "common-core/minitalk.pdf": [("Makefile",)], "post-common-core/lem_in.pdf": [("Makefile",)],
    "rncp/abstract_data.pdf": [("Makefile",)], "rncp/boot2root.pdf": [("writeup1", "writeup2")], "rncp/ft_ality.pdf": [("Makefile",)],
    "rncp/ft_nmap.pdf": [("Makefile",)], "rncp/ft_ping.pdf": [("Makefile",)], "rncp/ft_script.pdf": [("Makefile",)],
    "rncp/ft_select.pdf": [("author",)], "rncp/ft_ssl_md5.pdf": [("Makefile",)], "rncp/ft_traceroute.pdf": [("Makefile",)],
    "rncp/gomoku.pdf": [("Makefile",)], "rncp/h42n42.pdf": [("Makefile", "Dockerfile", "docker-compose.yml", "src/", "static/")],
    "rncp/kfs3.pdf": [("Makefile",)], "rncp/leaffliction.pdf": [("signature.txt",)],
    "rncp/libftpp.pdf": [("Makefile", "libftpp.hpp", "data_structures.hpp", "design_patterns.hpp", "threading.hpp", "network.hpp", "mathematics.hpp")],
    "rncp/nm.pdf": [("Makefile",)], "rncp/strace.pdf": [("Makefile",)],
}


def test_the_library_of_subjects_gives_exactly_the_reviewed_text_requirements():
    if not (REAL / "common-core").is_dir():
        pytest.skip("the library is not here")
    found = {}
    for pdf in sorted(REAL.rglob("*.pdf")):
        if pdf.name == "en.norm.pdf":
            continue
        rules = [r for r in parse_subject(pdf.name, read_pages(pdf)).rules if r.kind == "required_files" and r.params.get("from_text")]
        if rules:
            found[f"{pdf.parent.name}/{pdf.name}"] = [tuple(e[0] for e in r.params["files"]) for r in rules]
    assert found == EXPECTED_FROM_TEXT


def test_the_library_gives_the_layout_and_root_details_a_human_checked():
    if not (REAL / "common-core").is_dir():
        pytest.skip("the library is not here")
    def rule(path):
        return next(r for r in parse_subject(Path(path).name, read_pages(REAL / path)).rules if r.kind == "required_files" and r.params.get("from_text"))
    assert rule("common-core/born2beroot.pdf").params["root"] == ["signature.txt"]
    assert rule("rncp/ft_select.pdf").params["root"] == ["author"] and rule("rncp/leaffliction.pdf").params["root"] == ["signature.txt"]
    inception = rule("common-core/inception.pdf").params
    assert inception["root"] == ["Makefile"] and "Makefile" not in inception["soft"] and "srcs/" in inception["soft"]       # the layout is an example
    assert rule("rncp/boot2root.pdf").params["soft"] == ["writeup1", "writeup2"]
    h42 = rule("rncp/h42n42.pdf")
    assert h42.section == "mandatory" and ".gitignore" not in [e[0] for e in h42.params["files"]]                          # (it is "optional but recommended")
    gnl = next(r for r in parse_subject("get_next_line.pdf", read_pages(REAL / "common-core" / "get_next_line.pdf")).rules if r.kind == "required_files")
    assert gnl.params["root"] == ["get_next_line.c", "get_next_line_utils.c", "get_next_line.h"]
    assert not [r for r in parse_subject("libft.pdf", read_pages(REAL / "common-core" / "libft.pdf")).rules if r.params.get("from_text")]   # a table already says it
