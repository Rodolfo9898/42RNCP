from verdict.subjects.spec import parse_subject
from verdict.subjects.spec.lines import read_lines
from verdict.subjects.spec.tables import cpp_exercise_rules, libft_part1, parse_tables, read_table


def test_bonus_section_is_tagged():
    pages = ["Chapter I\nMandatory part\nProgram Name\nfoo\nDescription\nx\n",
             "Chapter II\nBonus part\nProgram Name\nbar\nFiles to Submit\n*.c\nDescription\ny\n"]
    spec = parse_subject("x.pdf", pages)
    sections = {r.params["program"]: r.section for r in spec.rules if r.kind == "program"}
    assert sections == {"foo": "mandatory", "bar": "bonus"}


def test_a_table_runs_from_its_first_label_to_the_description_and_its_field_lines_are_joined():
    lines = read_lines(["Chapter I\nMandatory part\nProgram Name\nfoo\nFiles to Submit\nMakefile,\n*.c\nDescription\nSomething else\n"])
    fields, after = read_table(lines, 0)
    assert fields == {"program": "foo", "files": "Makefile, *.c"}
    assert lines[after].text == "Something else"


def test_a_program_table_gives_its_files_makefile_rules_program_and_functions_in_this_order():
    pages = ["Chapter V\nMandatory part\nProgram Name\nphilo\nFiles to Submit\nMakefile, *.c in the directory philo/\nMakefile\nNAME, all, clean\n"
             "External Function\nmemset, printf, write\nLibft authorized\nNo\nDescription\nx\n"]
    rules = parse_tables(read_lines(pages), "philo.pdf")
    assert [r.kind for r in rules] == ["required_files", "makefile_rules", "program", "allowed_functions"]
    assert {r.unit for r in rules} == {"philo"}
    assert rules[0].params["files"] == [["Makefile"], ["*.c"]] and rules[1].params["targets"] == ["NAME", "all", "clean"]
    assert rules[3].params["functions"] == ["memset", "printf", "write"] and rules[3].params["libft"] is False


def test_a_files_field_with_only_prose_is_a_manual_item_and_a_functions_field_that_points_below_gives_no_rule():
    pages = ["Chapter V\nMandatory part\nProgram Name\nfoo\nFiles to Submit\nwhatever you need\nExternal Function\nsee the functions detailed below\nDescription\nx\n"]
    kinds = [r.kind for r in parse_tables(read_lines(pages), "foo.pdf")]
    assert kinds == ["manual", "program"]


def test_function_tables_are_summed_up_in_one_allowed_functions_rule_and_one_functions_defined_rule_per_part():
    pages = ["Chapter V\nMandatory part\nFunction name\nft_one\nFiles to Submit\none.c\nExternal functs.\nmalloc\nDescription\nx\n"
             "Function name\nft_two\nFiles to Submit\ntwo.c\nExternal functs.\nmalloc, free\nDescription\ny\n"
             "Chapter VI\nBonus part\nFunction name\nft_bonus\nExternal functs.\nnone\nDescription\nz\n"]
    rules = parse_tables(read_lines(pages), "x.pdf")
    assert [r.kind for r in rules] == ["required_files", "required_files", "allowed_functions", "functions_defined", "functions_defined"]
    allowed = [r for r in rules if r.kind == "allowed_functions"]
    assert [(r.section, r.params["functions"]) for r in allowed] == [("mandatory", ["malloc", "free"])]     # the bonus part allows nothing: no rule
    defined = {r.section: r.params["names"] for r in rules if r.kind == "functions_defined"}
    assert defined == {"mandatory": ["ft_one", "ft_two"], "bonus": ["ft_bonus"]}


def test_libft_lists_the_functions_of_its_first_part_as_bullets():
    lines = read_lines(["Chapter V\nMandatory part\nPart 1 - Libc functions\n• isalpha\n• strlen\nPart 2 - Additional functions\n• substr\n"])
    assert libft_part1(lines) == ["ft_isalpha", "ft_strlen"]


def test_each_cpp_exercise_gives_its_files_a_build_unit_and_the_makefile_rules():
    lines = read_lines(["Chapter V\nExercise 00\nDirectory: ex00/\nFiles to Submit: Makefile, main.cpp,\nZombie.{h, hpp}\n"
                        "Chapter VI\nExercise 01\nDirectory: ex01/\nFiles to Submit: Makefile, main.cpp\n"])
    rules = cpp_exercise_rules(lines, "cpp01.pdf")
    assert [(r.kind, r.unit) for r in rules] == [("required_files", "ex00"), ("build_unit", "ex00"), ("makefile_rules", "ex00"),
                                                 ("required_files", "ex01"), ("build_unit", "ex01"), ("makefile_rules", "ex01")]
    assert rules[0].params["files"] == [["Makefile"], ["main.cpp"], ["Zombie.h", "Zombie.hpp"]]
