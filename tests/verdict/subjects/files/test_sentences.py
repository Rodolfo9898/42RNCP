import pytest

from verdict.subjects.spec.files import sentence_files


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
    assert sentence_files(sentence) == (names, root)


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
    assert sentence_files(sentence) == ([], False)
