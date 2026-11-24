"""norminette's report, read from its output."""

from verdict.checks import Ctx
from verdict.checks.norm.checkers import NoGlobalsChecker, NormChecker
from verdict.checks.norm.report import NormError, NormReport, norm_report
from verdict.core.models import Rule
from verdict.gateways.sandbox import ExecResult

from tests.verdict.checks.helpers import answer, project

OUTPUT = (
    "a.c: Error!\n"
    "Error: TOO_MANY_LINES      (line:  12, col:   1):\tFunction has more than 25 lines\n"
    "\x1b[31mError: GLOBAL_VAR_DETECTED     (line:   3, col:   1):\tGlobal variable present in file\x1b[0m\n"
    "b.h: OK!\n"
    "c.c: Error!\n"
    "Notice: GLOBAL_VAR_DETECTED  (line:   9, col:   5):\tGlobal variable present in file. Make sure it is a reasonable choice.\n"
)


class Norminette:
    def __init__(self, output="", rc=1):
        self.output, self.rc, self.argv = output, rc, []

    def exec(self, argv, cwd, timeout=60, stdin=""):
        self.argv.append(argv)
        return ExecResult(rc=self.rc, stdout=self.output)


def ctx_with(repo, sandbox, lang="c"):
    return Ctx(repo=repo.resolve(), rules=[], sandbox=sandbox, lang=lang)


def test_the_errors_and_notices_of_each_file_are_read_from_the_output():
    report = NormReport(files=3)
    report.read(OUTPUT)
    assert report.errors == {
        "a.c": [NormError("TOO_MANY_LINES", 12, "Function has more than 25 lines", "Error"),
                NormError("GLOBAL_VAR_DETECTED", 3, "Global variable present in file", "Error")],
        "c.c": [NormError("GLOBAL_VAR_DETECTED", 9, "Global variable present in file. Make sure it is a reasonable choice.", "Notice")]}


def test_the_report_is_made_once_per_review_for_the_c_files_in_batches(tmp_path):
    repo = project(tmp_path, [f"f{i}.c" for i in range(130)], "libft.h", "notes.txt")
    sandbox = Norminette(OUTPUT)
    ctx = ctx_with(repo, sandbox)
    report = norm_report(ctx)
    assert norm_report(ctx) is report and ctx.cache["norm"] is report
    assert [len(argv) - 1 for argv in sandbox.argv] == [100, 31] and report.files == 131 and report.available


def test_a_sandbox_without_norminette_makes_the_report_unavailable(tmp_path):
    report = norm_report(ctx_with(project(tmp_path, ["a.c"]), Norminette(rc=127)))
    assert not report.available and report.files == 1


def test_only_the_errors_count_against_the_project_not_the_notices(tmp_path):
    repo = project(tmp_path, ["a.c", "c.c"])
    rule = Rule(id="n", kind="norm", title="Passes norminette")
    r = answer(NormChecker(), repo, rule, sandbox=Norminette(OUTPUT))
    assert r.status == "fail" and "2 Norm error(s) in 1 of 2 file(s)" in r.detail
    assert [(e.file, e.line, e.snippet) for e in r.evidence] == [("a.c", 12, "TOO_MANY_LINES: Function has more than 25 lines"),
                                                                  ("a.c", 3, "GLOBAL_VAR_DETECTED: Global variable present in file")]
    ok = answer(NormChecker(), project(tmp_path / "ok", ["a.c"]), rule, sandbox=Norminette("a.c: OK!\n", rc=0))
    assert ok.status == "pass" and ok.detail == "norminette: all 1 file(s) OK."


def test_global_variables_come_from_the_same_report(tmp_path):
    rule = Rule(id="g", kind="no_globals", title="No global variables", text="No global variables.")
    r = answer(NoGlobalsChecker(), project(tmp_path, ["a.c", "c.c"]), rule, sandbox=Norminette(OUTPUT))
    assert r.status == "fail" and "2 global variable(s)" in r.detail
    unavailable = answer(NoGlobalsChecker(), project(tmp_path / "u", ["a.c"]), rule, sandbox=Norminette(rc=127))
    assert (unavailable.status, unavailable.auto) == ("manual", False)


def test_the_norm_is_not_for_cpp_and_without_files_or_norminette_it_says_so(tmp_path):
    rule = Rule(id="n", kind="norm", title="Passes norminette")
    assert answer(NormChecker(), project(tmp_path / "a", ["a.c"]), rule, lang="cpp").detail == "The Norm does not apply to C++ projects."
    assert answer(NoGlobalsChecker(), project(tmp_path / "b", ["a.c"]), rule, lang="cpp").detail == "Not checked for C++ projects."
    assert answer(NormChecker(), project(tmp_path / "c", ["README.md"]), rule, sandbox=Norminette()).detail == "No .c/.h files to check."
    assert answer(NormChecker(), project(tmp_path / "d", ["a.c"]), rule, sandbox=Norminette(rc=127)).detail == "norminette is not installed in the sandbox."
