import pytest

from verdict.subjects.spec import parse_subject
from verdict.subjects.spec.lines import read_lines
from verdict.subjects.spec.prose import Sentence, default_chain, prose_items


def test_manual_rules_are_not_merged_together():
    spec = parse_subject("x.pdf", ["Chapter I\nRules\nYou must do the first thing properly.\nYou must also do the second thing.\n"])
    manual = [r for r in spec.rules if r.kind == "manual"]
    assert len(manual) == 2


def test_how_the_subject_is_graded_is_not_a_requirement_of_the_project():
    """Sentences about the bonus being judged only if the mandatory part is perfect, or about sections "that may be required", are not
    items for a human to check: nothing in the repository can satisfy them."""
    pages = ["Chapter V\nMandatory part\n"
             "Inside a window, the 3D object must be displayed in perspective and you must be able to rotate it.\n"
             "Additional sections may be required depending on the project (e.g., usage examples, feature list).\n"
             "Any required additions will be explicitly listed below.\n"
             "Chapter VI\nBonus part\n"
             "The bonus section will only be evaluated if the mandatory part is PERFECT. Perfect means everything works.\n"
             "If you miss even one mandatory feature, the bonus won’t be considered at all.\n"
             "The bonus must also support a second object, loaded at run time.\n"]
    texts = [r.text for r in parse_subject("scop.pdf", pages).rules if r.kind == "manual"]
    assert any("3D object must be displayed" in t for t in texts)
    assert any("bonus must also support a second object" in t for t in texts)         # a real bonus requirement stays
    for gone in ("Additional sections may be required", "Any required additions", "will only be evaluated", "won’t be considered"):
        assert not any(gone in t for t in texts), gone


def test_the_chapters_about_the_introduction_hold_no_requirement():
    pages = ["Chapter I\nIntroduction\nYou must be curious about this very long introduction sentence.\n"
             "Chapter II\nRules\nYou must write the first thing carefully.\n"]
    texts = [r.text for r in parse_subject("x.pdf", pages).rules if r.kind == "manual"]
    assert texts == ["You must write the first thing carefully."]


def sentence(text, module=None):
    return Sentence(text, read_lines(["Chapter I\nRules\n" + text])[0], "x.pdf", module)


@pytest.mark.parametrize("text,kind,params", [
    ("Your code must compile with the flags -Wall -Wextra -Werror using cc.", "flags", {"flags": ["-Wall", "-Wextra", "-Werror"], "compiler": "cc"}),
    ("Compile your code with c++98 and the flags -Wall -Wextra -Werror.", "flags", {"flags": ["-Wall", "-Wextra", "-Werror"], "compiler": "c++"}),
    ("Your code must still compile with -std=c++98 at the end.", "std98", {}),
    ("Your project must be written in accordance with the Norm.", "norm", {}),
    ("Your Makefile must not perform unnecessary relinking.", "no_relink", {}),
    ("Your Makefile must contain at least the rules $(NAME), all, clean, fclean and re.", "makefile_rules", {"targets": ["NAME", "all", "clean", "fclean", "re"]}),
    ("Your program must not quit unexpectedly in any case.", "no_crash", {}),
    ("Your project must be written in C and nothing else.", "language", {"lang": "c"}),
    ("All heap allocated memory must be properly freed when needed.", "no_leaks", {}),
    ("Global variables are forbidden in this project, no matter what.", "no_globals", {}),
    ("To submit bonuses for your project, you must include a bonus rule in your Makefile.", "bonus_rule", {}),
    ("The functions *printf(), *alloc() and free() are forbidden here.", "cpp_forbidden_calls", {"names": ["printf", "alloc", "free"]}),
    ("The keywords using namespace and friend are forbidden in the project.", "cpp_forbidden_keywords", {}),
    ("The STL only in modules 08 and 09, never before that.", "cpp_no_stl", {"module": 5}),
    ("A README.md file must be provided at the root of your Git repository.", "readme", {"sections": ["Description", "Instructions", "Resources"]}),
    ("Headers must have include guards to protect them from double inclusion.", "include_guards", {}),
    ("You can copy the sources of your libft into a folder of the repository.", "libft_copy", {}),
])
def test_the_chain_gives_each_general_rule_its_kind_and_parameters(text, kind, params):
    rule = default_chain().rule_for(sentence(text, module=5))
    assert rule is not None and rule.kind == kind and rule.params == params
    assert rule.text == text and rule.sources[0].pdf == "x.pdf" and rule.sources[0].page == 1


def test_the_first_extractor_of_the_chain_that_takes_a_sentence_wins():
    both = "Your Makefile must contain at least the rules all and re and compile with -Wall -Wextra -Werror."
    assert default_chain().rule_for(sentence(both)).kind == "flags"
    assert default_chain().rule_for(sentence("Nothing to see here, just a sentence about something.")) is None


def test_the_norm_extractor_leaves_out_the_goodbye_and_the_global_one_leaves_out_a_single_allowed_global():
    assert default_chain().rule_for(sentence("Goodbye: the Norm must be followed in accordance with the norm, so long.")) is None
    assert default_chain().rule_for(sentence("Global variables are forbidden, except one global variable for your signals.")) is None


def test_wrapped_lines_become_sentences_and_bullets_become_items():
    lines = read_lines(["Chapter I\nRules\n• You must write a first rule that is\nlong enough to be wrapped. Then it goes on and on with more text\n"
                        "• A second bullet that is long enough too.\n"])
    assert [text for text, _ in prose_items(lines)] == ["You must write a first rule that is long enough to be wrapped.",
                                                         "Then it goes on and on with more text", "A second bullet that is long enough too."]
