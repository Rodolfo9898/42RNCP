from verdict.core.models import AIReview, AIState, CheckResult, ClaudeReport, ClaudeVerdict, Correction, Improvement
from verdict.reports.report import render_markdown
from verdict.reports.report.markdown.text import inline
from tests.verdict.reports.report.helpers import manual, result


def test_inline_keeps_code_spans_and_escapes_everything_else():
    assert inline("`make` builds `push_swap`") == "`make` builds `push_swap`"
    assert inline("a_b *c* [d] <e> | f") == r"a\_b \*c\* \[d\] \<e\> \| f"
    assert inline("stray ` tick <img src=x>") == r"stray \` tick \<img src=x\>"
    assert inline("`a` <b> `c`") == r"`a` \<b\> `c`"


def test_untrusted_text_cannot_inject_html_or_headings():
    evil = Improvement(category="code", title="<script>alert(1)</script> `x", detail="<img src=x onerror=1>\n# heading")
    md = render_markdown(repo=None, subjects=["<b>x</b>.pdf"], results=[result("fail", title="<i>t</i>", detail="a\n## b")], improvements=[evil])
    for line in md.splitlines():
        assert "<script" not in line.replace("\\<", "") and "<img" not in line.replace("\\<", "")
        assert not line.startswith("## b") and not line.startswith("# heading")


def test_text_from_claude_cannot_inject_markup():
    results = [CheckResult(rule_id="r1", title="Needs manual review", status="manual", detail="Normal requirement.")]
    ai = AIState(reviews={"r1": AIReview(rule_id="r1", assessment="likely_problem", finding="<img src=x onerror=alert(1)> # heading",
                                         why_manual="[click](javascript:alert(1))", by="Claude")})
    claude = ClaudeReport(structured=True, corrections=[Correction(check="<b>x</b>", says="<i>", actually="a_b *c*")],
                          verdict=ClaudeVerdict(decision="do not pass", reason="<script>x</script>"))
    md = render_markdown(repo=None, subjects=[], results=results, ai=ai, claude=claude)
    for line in md.splitlines():
        assert "<img" not in line.replace("\\<", "") and "<script" not in line.replace("\\<", "") and "<b>" not in line.replace("\\<", "")
        assert not line.startswith("# heading")
    assert "[click]" not in md.replace("\\[click\\]", "")


def test_escaping_still_protects_names_with_underscores_and_stars():
    results = [CheckResult(rule_id="r1", title="Needs manual review", status="manual", detail="ft_strchr and ft_*.c must exist.")]
    ai = AIState(reviews={"r1": AIReview(rule_id="r1", assessment="likely_problem", finding="ft_strchr.c is wrong", by="Claude")})
    md = render_markdown(repo=None, subjects=[], results=results, ai=ai)
    assert "ft\\_strchr and ft\\_\\*.c must exist." in md and "ft\\_strchr.c is wrong" in md
