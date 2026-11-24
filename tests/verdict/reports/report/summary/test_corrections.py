import pytest

from verdict.core.models import CheckResult, Correction, Evidence
from verdict.reports.report import corrected, render_markdown, summarize
from tests.verdict.reports.report.helpers import fix_of, manual, report_with, result, section


@pytest.mark.parametrize("status,shown", [("likely_ok", "pass"), ("likely_problem", "fail"), ("unclear", "warn"), ("not_applicable", "na")])
def test_a_correction_replaces_the_status_the_text_and_the_log(status, shown):
    script = result("fail", title="Compiles", detail="the script's words", log="the script's log", evidence=[Evidence(file="a.c", line=1)])
    out = corrected([script], report_with(fix_of("Compiles", status, evidence=[Evidence(file="b.c", line=2)])))
    assert len(out) == 1
    assert (out[0].status, out[0].detail, out[0].log, out[0].by, out[0].title) == (shown, "what is true", "", "Claude", "Compiles")
    assert [e.file for e in out[0].evidence] == ["b.c"]
    assert script.detail == "the script's words" and script.by == "script"          # the session keeps what the scripts said


def test_a_check_that_passed_can_be_overwritten_as_a_failure():
    md = render_markdown(repo=None, subjects=[], results=[result("pass", title="Does not crash", detail="8 runs")],
                         claude=report_with(fix_of("Does not crash", "likely_problem", "Segfaults on an empty file.")))
    lacking = section(md, "## ❌ Lacking", "## ⚠️ Second look")
    assert "**Does not crash** `Claude` — Segfaults on an empty file." in lacking and "8 runs" not in md


def test_a_skipped_check_that_claude_tested_stops_being_a_second_look():
    results = [result("skipped", title="No memory leaks", detail="No executable was built.")]
    md = render_markdown(repo=None, subjects=[], results=results, claude=report_with(fix_of("No memory leaks", "likely_ok", "valgrind is clean.")))
    assert "No executable was built" not in md and summarize(results, None, report_with(fix_of("No memory leaks")))["overall"] == "PASS"


@pytest.mark.parametrize("check", [
    "`make clean` keeps the program", "make clean keeps the program", "`MAKE CLEAN` keeps  the program",
    "`make clean` keeps the program: `make clean` also removed the program(s): x.o", "`make clean` keeps the program — also removed", "`make clean` keeps th…",
])
def test_claude_may_name_a_check_the_way_the_prompts_print_it(check):
    out = corrected([result("fail", title="`make clean` keeps the program", detail="also removed")], report_with(fix_of(check)))
    assert len(out) == 1 and out[0].status == "pass"


def test_a_longer_title_is_not_mistaken_for_a_shorter_one():
    results = [result("fail", title="Makefile"), result("fail", title="Makefile rules")]
    assert [r.status for r in corrected(results, report_with(fix_of("Makefile rules")))] == ["fail", "pass"]


def test_a_requirement_can_be_overwritten_by_its_sentence():
    manual = [CheckResult(rule_id="a", title="Needs manual review", status="manual", detail="Must  not relink."),
              CheckResult(rule_id="b", title="Needs manual review", status="manual", detail="Must not relink.")]
    out = corrected(manual, report_with(fix_of("Must not relink.", "likely_problem", "It relinks.")))
    assert [(r.title, r.status, r.detail) for r in out] == [("Must not relink.", "fail", "It relinks.")]


def test_a_finding_about_nothing_known_is_added_where_its_status_says():
    results = [result("pass", title="Required files")]
    claude = report_with(fix_of("Reads past the buffer", "likely_problem", "main.c overflows."), fix_of("Bonus leaks", "likely_problem", "x", section="bonus"))
    out = corrected(results, claude)
    assert [(r.title, r.status, r.section, r.by) for r in out[1:]] == [("Reads past the buffer", "fail", "mandatory", "Claude"), ("Bonus leaks", "fail", "bonus", "Claude")]
    assert "**Reads past the buffer** `Claude` — main.c overflows." in section(render_markdown(repo=None, subjects=[], results=results, claude=claude), "## ❌ Lacking", "## ⚠️")


def test_a_correction_without_a_status_is_a_second_look():
    results = [result("fail", title="Norm", detail="3 errors")]
    md = render_markdown(repo=None, subjects=[], results=results, claude=report_with(Correction(check="Norm", actually="they are vendored")))
    second = section(md, "## ⚠️ Second look", "## ✅ Ok")
    assert "Claude is unsure (1)" in second and "they are vendored" in second and "3 errors" not in md
