from verdict.subjects.spec import LABELS, MATH_FUNCTIONS, label_of
from verdict.subjects.spec.vocabulary import identifiers


def test_a_table_label_is_read_whatever_its_case_colon_or_spacing():
    assert label_of("Program Name") == label_of("  program name: ") == "program"
    assert label_of("External functs.") == "functions" and label_of("Turn-in files") == "files"
    assert label_of("Something else") is None and set(LABELS.values()) >= {"program", "files", "makefile", "functions", "libft"}


def test_the_math_library_is_every_function_it_exports():
    assert {"sin", "pow", "sqrt", "fmod", "cexp", "fesetround"} <= set(MATH_FUNCTIONS)


def test_the_names_in_a_functions_field_are_listed_once_in_order_and_without_the_words_around_them():
    assert identifiers("write, malloc and free or any equivalent, write") == ["write", "malloc", "free"]
    assert identifiers("none") == [] and identifiers("ft_printf (your own)") == ["ft_printf"]
