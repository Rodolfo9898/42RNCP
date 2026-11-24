from verdict.core.models import AIReview, AIState, CheckResult, ClaudeReport, ClaudeVerdict, Correction, Evidence, Improvement, Source
from verdict.reports.report import render_markdown, summarize


def result(status, title="T", detail="", section="mandatory", **kw):
    return CheckResult(rule_id=None, title=title, status=status, detail=detail, section=section, **kw)


def manual(rule_id, detail):
    return CheckResult(rule_id=rule_id, title="Needs manual review", status="manual", detail=detail)


def judged(**assessments):
    return AIState(reviews={rid: AIReview(rule_id=rid, assessment=a, by="Claude") for rid, a in assessments.items()})


def merged_document():
    results = [
        result("fail", title="README.md meets the subject's requirements", detail="No README.md found."),
        result("fail", title="Makefile has a bonus rule", detail="no bonus files in the repository"),
        result("pass", title="Required files", detail="all there"),
        result("skipped", title="Passes norminette", detail="norminette is not installed."),
        CheckResult(rule_id="r1", title="Needs manual review", status="manual", detail="The strchr function must find any byte.", sources=[Source(pdf="libft.pdf", page=9)]),
        CheckResult(rule_id="r2", title="Needs manual review", status="manual", detail="The Makefile must not relink.", sources=[Source(pdf="libft.pdf", page=4)]),
        CheckResult(rule_id="r3", title="Needs manual review", status="manual", detail="Bonuses live in separate bonus files.", sources=[Source(pdf="libft.pdf", page=4)]),
        CheckResult(rule_id="r4", title="Needs manual review", status="manual", detail="Applies to projects that use libft.", sources=[Source(pdf="libft.pdf", page=4)]),
        CheckResult(rule_id="r5", title="Needs manual review", status="manual", detail="Claude never got to this one.", sources=[Source(pdf="libft.pdf", page=5)]),
        CheckResult(rule_id="r6", title="Needs manual review", status="manual", detail="No crash on normal input.", sources=[Source(pdf="libft.pdf", page=4)]),
    ]
    ai = AIState(reviews={
        "r1": AIReview(rule_id="r1", assessment="likely_problem", finding="Bytes above 0x7f are missed on signed-char platforms.", why_manual="Run it on x86.",
                       evidence=[Evidence(file="ft_strchr.c", line=20)], by="Claude"),
        "r2": AIReview(rule_id="r2", assessment="unclear", finding="bonus relinks every time.", by="Claude"),
        "r3": AIReview(rule_id="r3", assessment="likely_ok", finding="Fine.", by="Claude"),
        "r4": AIReview(rule_id="r4", assessment="not_applicable", finding="Later projects.", by="Claude"),
        "r6": AIReview(rule_id="r6", assessment="likely_ok", finding="valgrind clean.", by="Claude", evidence=[Evidence(file="main.c", line=3)]),
    })
    claude = ClaudeReport(
        structured=True, assessed=5, total=6,
        corrections=[Correction(check="Makefile has a bonus rule", says="no bonus files in the repository", actually="The list functions are built by `make bonus`.", status="likely_ok")],
        verdict=ClaudeVerdict(decision="do not pass", reason="The README is missing and strchr is wrong."),
        improvements=[Improvement(category="code", priority="high", title="Fix strchr", detail="Compare as char.", evidence=[Evidence(file="ft_strchr.c", line=20)], source="ai")],
        problems=["Claude did not answer 1 of 6 requirement(s): #5."])
    return render_markdown(repo=None, subjects=["libft.pdf"], results=results, improvements=claude.improvements, ai=ai,
                           claude_review="# prose that must not be repeated", claude=claude, project="libft")


def section(md, start, end):
    return md[md.index(start):md.index(end)]


def decided(decision, results, **kw):
    claude = ClaudeReport(structured=True, verdict=ClaudeVerdict(decision=decision, reason="Because."), **kw)
    return summarize(results, judged(), claude), claude


def fix_of(check, status="likely_ok", actually="what is true", **kw):
    return Correction(check=check, status=status, actually=actually, **kw)


def report_with(*corrections, decision=None, **kw):
    verdict = ClaudeVerdict(decision=decision, reason="Because.") if decision else None
    return ClaudeReport(structured=True, corrections=list(corrections), verdict=verdict, **kw)
