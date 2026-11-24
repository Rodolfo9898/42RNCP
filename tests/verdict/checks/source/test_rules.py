"""What the sources are written in, and what they may not call, name or include."""

from verdict.checks.source.cpp import CppForbiddenCallsChecker, CppForbiddenKeywordsChecker, CppNoStlChecker
from verdict.checks.source.language import IncludeGuardsChecker, LanguageChecker
from verdict.core.models import Rule

from tests.verdict.checks.helpers import answer, project


def run(checker, repo, kind, **params):
    return answer(checker, repo, Rule(id=kind, kind=kind, title=kind, params=params))


def test_a_forbidden_call_is_found_in_the_code_but_not_in_a_comment_or_a_string(tmp_path):
    repo = project(tmp_path, {"a.cpp": '// printf("no")\nconst char *s = "free(";\nint main() { char *p = (char *)malloc(2); free(p); }\n'})
    r = run(CppForbiddenCallsChecker(), repo, "cpp_forbidden_calls")
    assert r.status == "fail" and [e.line for e in r.evidence] == [3]
    assert run(CppForbiddenCallsChecker(), project(tmp_path / "ok", {"b.cpp": "int main() { return a.free(); }\n"}), "cpp_forbidden_calls").status == "pass"


def test_using_namespace_and_friend_are_refused(tmp_path):
    bad = run(CppForbiddenKeywordsChecker(), project(tmp_path / "a", {"a.hpp": "using namespace std;\nclass A { friend class B; };\n"}), "cpp_forbidden_keywords")
    assert bad.status == "fail" and [e.line for e in bad.evidence] == [1, 2]
    assert run(CppForbiddenKeywordsChecker(), project(tmp_path / "b", {"a.hpp": "class A {};\n"}), "cpp_forbidden_keywords").status == "pass"


def test_the_stl_is_refused_before_module_08_and_allowed_from_it(tmp_path):
    repo = project(tmp_path, {"a.cpp": "#include <vector>\n// #include <map>\n"})
    early = run(CppNoStlChecker(), repo, "cpp_no_stl", module=3)
    assert early.status == "fail" and [e.line for e in early.evidence] == [1, 2]            # a header in a comment is still listed: the text is read as is
    assert run(CppNoStlChecker(), repo, "cpp_no_stl", module=8).status == "skipped"
    assert run(CppNoStlChecker(), repo, "cpp_no_stl").status == "skipped"
    assert run(CppNoStlChecker(), project(tmp_path / "ok", ["a.cpp"]), "cpp_no_stl", module=2).status == "pass"


def test_cpp_files_do_not_belong_in_a_c_project_but_scripts_do(tmp_path):
    wrong = run(LanguageChecker(), project(tmp_path / "a", ["main.c", "x.cpp"]), "language")
    assert wrong.status == "fail" and wrong.detail == "C++ files found in a C project."
    assert run(LanguageChecker(), project(tmp_path / "b", ["README.md"]), "language").detail == "No .c files found."
    mixed = run(LanguageChecker(), project(tmp_path / "c", ["main.c", "tests/run.py"]), "language")
    assert mixed.status == "pass" and "1 file(s) in other languages" in mixed.detail and mixed.evidence[0].file == "tests/run.py"
    assert run(LanguageChecker(), project(tmp_path / "d", ["main.c"]), "language").detail == "Only C sources found."


def test_every_header_needs_a_guard(tmp_path):
    guarded = {"a.h": "#ifndef A_H\n# define A_H\n#endif\n", "b.h": "#pragma once\n"}
    assert run(IncludeGuardsChecker(), project(tmp_path / "a", guarded), "include_guards").detail == "All 2 header(s) have include guards."
    bad = run(IncludeGuardsChecker(), project(tmp_path / "b", {**guarded, "c.h": "int x;\n"}), "include_guards")
    assert bad.status == "fail" and "1 of 3 header(s)" in bad.detail and bad.evidence[0].file == "c.h"
    assert run(IncludeGuardsChecker(), project(tmp_path / "c", ["main.c"]), "include_guards").status == "skipped"
