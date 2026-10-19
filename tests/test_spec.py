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
