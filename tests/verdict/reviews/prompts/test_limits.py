from tests.verdict.reviews.prompts.samples import build, fix, r


def test_the_fix_prompt_lists_what_the_subject_allows_and_forbids_adding_anything_else():
    from verdict.core.models import Rule, Source
    rules = [Rule(id="a", kind="allowed_functions", title="x", text="t", sources=[Source(pdf="so_long.pdf", page=3)],
                  params={"functions": ["write", "malloc", "free"], "libft": True, "math": False, "mlx": True, "own_allowed": False}),
             Rule(id="b", kind="manual", title="m", text="The use of external libraries is forbidden, except the standard library."),
             Rule(id="c", kind="manual", title="n", text="Your program must print a newline at the end.")]
    prompt, _ = fix([r("fail", "Required files", "Missing: a.c")], rules=rules)
    assert "External functions allowed (so_long.pdf p.3): write, malloc, free; also the project's own libft, MiniLibX" in prompt
    assert "The use of external libraries is forbidden" in prompt and "newline at the end" not in prompt      # only what limits the code
    assert "Do not add a library, a dependency or an external function the subject does not allow" in prompt
    assert "Dependencies added: none" in prompt and "report it as not fixed" in prompt


def test_without_a_list_in_the_subject_nothing_new_may_be_added():
    prompt, _ = fix([r("fail", "Required files", "Missing: a.c")])
    assert "add nothing that is not already used by the project" in prompt


def test_the_review_prompt_knows_the_limits_too():
    from verdict.core.models import Rule
    rules = [Rule(id="a", kind="cpp_forbidden_keywords", title="No `using namespace` or `friend`")]
    prompt, _ = build(rules=rules)
    assert "Forbidden: No `using namespace` or `friend`" in prompt and "report any use of something outside these limits" in prompt
