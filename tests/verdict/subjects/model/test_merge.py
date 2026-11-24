from tests.conftest import NORM_PAGES, SUBJECT_PAGES
from verdict.subjects.spec import merge_rules, parse_norm, parse_subject
from verdict.subjects.spec.model import make_rule


def test_merge_remembers_all_sources():
    a = parse_subject("a.pdf", SUBJECT_PAGES)
    b = parse_subject("b.pdf", SUBJECT_PAGES)
    merged = merge_rules(a.rules + b.rules)
    assert len(merged) == len(a.rules)
    assert {s.pdf for s in merged[0].sources} == {"a.pdf", "b.pdf"}


def test_norm_rule_merges_with_the_subjects_own():
    norm = next(r for r in parse_norm("en.norm.pdf", NORM_PAGES).rules if r.kind == "norm")
    own = next(r for r in parse_subject("push_swap.pdf", SUBJECT_PAGES).rules if r.kind == "norm")
    merged = merge_rules([own, norm])
    assert len(merged) == 1 and {s.pdf for s in merged[0].sources} == {"push_swap.pdf", "en.norm.pdf"}


def test_merging_leaves_the_rules_it_was_given_alone():
    rule = make_rule("norm", "Passes norminette")
    merge_rules([rule, make_rule("norm", "Passes norminette")])
    assert rule.sources == []


def test_the_id_of_a_rule_depends_on_what_it_asks_and_not_on_its_wording_or_origin():
    first = make_rule("makefile_rules", "Makefile rules", text="one", params={"targets": ["all", "re"]})
    same = make_rule("makefile_rules", "Other title", text="two", params={"targets": ["all", "re"]})
    other = make_rule("makefile_rules", "Makefile rules", text="one", params={"targets": ["all"]})
    assert first.id == same.id and first.id.startswith("makefile_rules:") and first.id != other.id
    assert make_rule("norm", "x", section="bonus").id != make_rule("norm", "x").id
