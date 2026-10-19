from pathlib import Path

from verdict.checks import Ctx, run_checks
from verdict.improve import functions, suggest
from verdict.spec import parse_subject

GOOD_README = """*This project has been created as part of the 42 curriculum by rodolfo.*

# push_swap

## Description
Sorts stacks.

## Instructions
Run `make`, then `./push_swap 3 2 1`.

## Resources
Documentation about sorting. AI was used to explain complexity classes; no code was generated.
"""


def ctx_for(repo: Path, lang="c", readme_required=False):
    rules = parse_subject("x.pdf", README_SUBJECT).rules if readme_required else []
    return Ctx(repo=repo.resolve(), rules=rules, sandbox=None, lang=lang)


def titles(improvements, category=None):
    return [i.title for i in improvements if category is None or i.category == category]


# ---------------------------------------------------------------- function parsing


def test_functions_found_in_42_style_code():
    code = "int\tft_a(int x)\n{\n\treturn (x);\n}\n\nstatic void\tb(void)\n{\n\tint i;\n\n\ti = 0;\n}\n"
    assert list(functions(code)) == [("ft_a", 2, 4), ("b", 7, 11)]


def test_structs_and_enums_are_not_functions():
    code = "typedef struct s_a\n{\n\tint x;\n}\tt_a;\n\nenum e\n{\n\tA,\n}\n\nint f(void)\n{\n\treturn (1);\n}\n"
    assert [name for name, _, _ in functions(code)] == ["f"]


def test_same_line_brace_and_nested_blocks():
    code = "int main(int ac, char **av) {\n    if (ac) {\n        return 1;\n    }\n    return 0;\n}\n"
    assert list(functions(code)) == [("main", 1, 6)]


# ---------------------------------------------------------------- structure


def test_missing_readme_is_called_out_first_when_the_subject_requires_it(tmp_path):
    (tmp_path / "main.c").write_text("int main(void)\n{\n\treturn (0);\n}\n")
    out = suggest(ctx_for(tmp_path, readme_required=True))
    assert out[0].title == "No README found" and out[0].priority == "high" and out[0].category == "structure"
    assert "requires" in out[0].detail and "Description" in out[0].detail and "Resources" in out[0].detail


def test_missing_readme_without_a_requirement_is_advice_about_explaining_the_project(tmp_path):
    (tmp_path / "main.c").write_text("int main(void)\n{\n\treturn (0);\n}\n")
    readme = next(i for i in suggest(ctx_for(tmp_path)) if i.title == "No README found")
    assert readme.priority == "medium"
    assert "None of the loaded subjects requires one" in readme.detail
    assert "how the code is organised" in readme.detail
    assert "italics" not in readme.detail and "Description" not in readme.detail   # no imposed structure


def test_readme_variants(tmp_path):
    (tmp_path / "readme.txt").write_text("hi\n")
    out = suggest(ctx_for(tmp_path, readme_required=True))
    assert "Rename readme.txt to README.md" in titles(out)
    (tmp_path / "readme.txt").unlink()
    (tmp_path / "README.md").write_text("# x\nshort\n")
    assert "README is very short" in titles(suggest(ctx_for(tmp_path)))
    (tmp_path / "README.md").write_text(GOOD_README * 2)
    assert not [t for t in titles(suggest(ctx_for(tmp_path))) if "README" in t]


def test_makefile_wildcard_and_phony(tmp_path):
    (tmp_path / "Makefile").write_text("SRCS = $(wildcard *.c)\nall:\n\tcc $(SRCS)\n")
    out = suggest(ctx_for(tmp_path))
    wild = next(i for i in out if "wildcard" in i.title)
    assert wild.evidence[0].line == 1 and wild.evidence[0].file == "Makefile"
    assert any(".PHONY" in t for t in titles(out))


def test_leftover_files_and_gitignore(tmp_path):
    for name in ("main.c", "main.c~", "a.out", "test_gnl.c"):
        (tmp_path / name).write_text("x\n")
    out = suggest(ctx_for(tmp_path))
    left = next(i for i in out if i.title == "Leftover or scratch files")
    assert {e.file for e in left.evidence} == {"main.c~", "a.out", "test_gnl.c"}
    assert "No .gitignore" in titles(out)


# ---------------------------------------------------------------- code / readability / logic


def test_long_functions_and_debug_leftovers(tmp_path):
    body = "\n".join(f"\tx += {i};" for i in range(45))
    (tmp_path / "main.c").write_text(
        f'int\tbig(int x)\n{{\n{body}\n\treturn (x);\n}}\n\nvoid\tf(void)\n{{\n\tprintf("DEBUG here\\n");\n\t// ft_free(p);\n\t// TODO later\n}}\n')
    out = suggest(ctx_for(tmp_path))
    big = next(i for i in out if "long function" in i.title)
    assert big.category == "readability" and big.evidence[0].snippet == "big(): 46 lines"
    assert any(i.title == "Debug output left in the code" and i.evidence[0].line == 53 for i in out)
    assert "Commented-out code" in titles(out) and "Unresolved TODO/FIXME notes" in titles(out)


def test_deep_nesting(tmp_path):
    (tmp_path / "a.c").write_text("void\tf(void)\n{\n" + "\t" * 6 + "x();\n}\n")
    assert "Deeply nested code" in titles(suggest(ctx_for(tmp_path)), "readability")


def test_unsafe_functions_only_flagged_in_real_code(tmp_path):
    (tmp_path / "a.c").write_text('void\tf(char *d, char *s)\n{\n\tstrcpy(d, s);\n\t// system("ls");\n\tft_strcpy(d, s);\n\tputs("gets(x)");\n}\n')
    unsafe = next(i for i in suggest(ctx_for(tmp_path)) if i.title.startswith("Functions that are easy"))
    assert [(e.line) for e in unsafe.evidence] == [3]


def test_unchecked_allocation_is_flagged_but_checked_is_not(tmp_path):
    (tmp_path / "a.c").write_text(
        "char\t*bad(void)\n{\n\tchar\t*p;\n\n\tp = malloc(10);\n\tp[0] = 'a';\n\treturn (p);\n}\n\n"
        "char\t*good1(void)\n{\n\tchar\t*p;\n\n\tp = malloc(10);\n\tif (!p)\n\t\treturn (NULL);\n\treturn (p);\n}\n\n"
        "char\t*good2(void)\n{\n\tchar\t*p;\n\n\tp = ft_strdup(\"x\");\n\tif (p == NULL)\n\t\treturn (NULL);\n\treturn (p);\n}\n")
    alloc = next(i for i in suggest(ctx_for(tmp_path)) if i.category == "logic")
    assert alloc.title == "Possible unchecked allocation" and alloc.priority == "high"
    assert [e.line for e in alloc.evidence] == [5]


def test_unchecked_open(tmp_path):
    (tmp_path / "a.c").write_text("void\tf(void)\n{\n\tint\tfd;\n\n\tfd = open(\"x\", O_RDONLY);\n\tread(fd, 0, 0);\n}\n")
    assert "Possible unchecked open()" in titles(suggest(ctx_for(tmp_path)), "logic")


def test_results_are_sorted_by_priority(tmp_path):
    (tmp_path / "a.c").write_text("void\tf(void)\n{\n\tchar *p;\n\n\tp = malloc(1);\n\tp[0] = 0;\n}\n")
    priorities = [i.priority for i in suggest(ctx_for(tmp_path))]
    assert priorities == sorted(priorities, key={"high": 0, "medium": 1, "low": 2}.get)


# ---------------------------------------------------------------- the README rule of the subject

README_SUBJECT = [
    "Chapter I\nReadme Requirements\nA README.md file must be provided at the root of your Git repository.\n"
    "The README.md must include at least:\n- The very first line must be italicized and read: This project has been created as part of the 42 curriculum by <login1>.\n"
]


def readme_result(repo: Path):
    spec = parse_subject("x.pdf", README_SUBJECT)
    assert [r.kind for r in spec.rules] == ["readme"], "the three README sentences must collapse into one rule"
    out = []
    run_checks(Ctx(repo=repo.resolve(), rules=spec.rules, sandbox=None, lang="c"), out.append)
    return next(r for r in out if r.title.startswith("README.md meets"))


def test_readme_rule_missing(tmp_path):
    (tmp_path / "main.c").write_text("x\n")
    r = readme_result(tmp_path)
    assert r.status == "fail" and "No README.md found" in r.detail


def test_readme_rule_wrong_name(tmp_path):
    (tmp_path / "readme.md").write_text(GOOD_README)
    r = readme_result(tmp_path)
    assert r.status == "fail" and "exactly README.md" in r.detail


def test_readme_rule_good_and_variants(tmp_path):
    (tmp_path / "README.md").write_text(GOOD_README)
    assert readme_result(tmp_path).status == "pass"
    (tmp_path / "README.md").write_text(GOOD_README.replace("*This project", "This project").replace("rodolfo.*", "rodolfo."))
    assert "italicized" in readme_result(tmp_path).detail
    (tmp_path / "README.md").write_text(GOOD_README.replace("rodolfo", "<login1>"))
    assert "placeholder" in readme_result(tmp_path).detail
    (tmp_path / "README.md").write_text(GOOD_README.replace("## Resources", "## Links"))
    r = readme_result(tmp_path)
    assert r.status == "fail" and "Resources" in r.detail
    (tmp_path / "README.md").write_text(GOOD_README.replace("AI was used to explain complexity classes; no code was generated.", "Some articles."))
    assert readme_result(tmp_path).status == "warn"
