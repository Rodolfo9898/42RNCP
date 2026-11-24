"""The external functions of the build, with the symbols `nm` prints on Linux (so these run everywhere)."""

from verdict.checks.functions.allowed import AllowedFunctionsChecker
from verdict.core.models import Rule
from verdict.gateways.sandbox import ExecResult

from tests.verdict.checks.helpers import answer, project

MAIN = "int main(int argc, char **argv)\n{\n\treturn ((int)strlen(argv[0]) + argc);\n}\n"
PROGRAM = Rule(id="p", kind="program", title="Builds push_swap", params={"program": "push_swap"})


class Nm:
    """A sandbox that only knows nm: the program imports `undefined`."""

    def __init__(self, undefined, defined=("main",)):
        self.undefined, self.defined = undefined, defined

    def exec(self, argv, cwd, timeout=60, stdin=""):
        assert argv[:2] == ["nm", "-g"]
        lines = [f"                 U {n}" for n in self.undefined] + [f"0000000000001139 T {n}" for n in self.defined] + ["                 w __gmon_start__"]
        return ExecResult(rc=0, stdout="\n".join(lines) + "\n")


def allowed(tmp_path, undefined, files=None, **params):
    repo = project(tmp_path, {"push_swap": "binary", "main.c": MAIN, **(files or {})})
    rule = Rule(id="a", kind="allowed_functions", title="Only authorized external functions", params={"functions": ["write"], **params})
    return answer(AllowedFunctionsChecker(), repo, rule, rules=[PROGRAM, rule], sandbox=Nm(undefined))


def test_a_forbidden_function_the_project_calls_is_named_with_its_location(tmp_path):
    r = allowed(tmp_path, ["write", "strlen"])
    assert r.status == "fail" and "not authorized: strlen" in r.detail
    assert [(e.file, e.line) for e in r.evidence] == [("main.c", 3)]


def test_what_a_library_imports_on_its_own_is_not_held_against_the_project(tmp_path):
    r = allowed(tmp_path, ["write", "getenv"])
    assert r.status == "pass" and "1 imported symbol(s) come from linked libraries" in r.detail


def test_the_functions_of_the_subject_and_its_libraries_are_allowed(tmp_path):
    assert allowed(tmp_path / "a", ["write", "_start", "__libc_start_main"]).detail == "No unauthorized function calls found."
    assert allowed(tmp_path / "b", ["write", "strlen"], files={"main.c": "int main(void)\n{\n\treturn (0);\n}\n"}, functions=["write", "strlen"]).status == "pass"
    assert allowed(tmp_path / "c", ["malloc", "free", "write"], libft=True).status == "pass"
    assert allowed(tmp_path / "d", ["fma", "sinf", "ceill"], math=True).status == "pass"
    assert allowed(tmp_path / "e", ["mlx_init", "XOpenDisplay", "shmget"], mlx=True).status == "pass"


def test_calls_the_compiler_makes_by_itself_are_not_the_students(tmp_path):
    r = allowed(tmp_path, ["memcpy", "memset"])
    assert r.status == "pass" and "Only compiler-generated calls to memcpy, memset" in r.detail


def test_cpp_is_left_to_a_human_and_nothing_built_is_skipped(tmp_path):
    repo = project(tmp_path, {"main.cpp": "int main() {}\n"})
    rule = Rule(id="a", kind="allowed_functions", title="x", text="the functions", params={"functions": []})
    manual = answer(AllowedFunctionsChecker(), repo, rule, sandbox=Nm([]), lang="cpp")
    assert (manual.status, manual.auto, manual.detail) == ("manual", False, "the functions")
    nothing = answer(AllowedFunctionsChecker(), repo, rule, sandbox=Nm([]))
    assert nothing.status == "skipped" and "Nothing was built" in nothing.detail
