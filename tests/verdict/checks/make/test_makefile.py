from verdict.checks import Ctx, run_checks
from verdict.checks.make.makefile import has_target
from verdict.core.models import Rule


def test_a_missing_bonus_rule_is_not_applicable_when_there_are_no_bonus_files(tmp_path):
    (tmp_path / "Makefile").write_text("all:\n\tcc main.c\n")
    (tmp_path / "main.c").write_text("int main(void) { return 0; }\n")
    rule = Rule(id="r1", kind="bonus_rule", title="Makefile has a bonus rule")
    out = []
    run_checks(Ctx(repo=tmp_path.resolve(), rules=[rule], sandbox=None, lang="c"), out.append)
    assert [r.status for r in out if r.rule_id == "r1"] == ["na"]


def test_a_target_is_a_rule_of_the_makefile_whatever_else_stands_on_its_line():
    makefile = "NAME = a.out\nall clean: $(NAME)\nre:\n.PHONY: all\nCC := cc\nfclean: clean\n"
    assert all(has_target(makefile, t) for t in ("NAME", "all", "clean", "re", "fclean"))
    assert not has_target(makefile, "bonus") and not has_target(makefile, "CC")        # a variable is not a rule


def test_name_may_be_a_variable_or_a_rule():
    assert has_target("NAME := push_swap\n", "NAME") and has_target("$(NAME): main.o\n", "NAME")
    assert not has_target("all:\n", "NAME")
