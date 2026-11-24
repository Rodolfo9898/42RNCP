"""Results of a check run, and the two prompts built from them."""

from verdict.core.models import CheckResult, Source
from verdict.reviews.prompts import build_fix_prompt, build_review_prompt

REPORT_DIR = "/scratch/reports/abc"


def r(status, title, detail="", pdf="push_swap.pdf", page=3):
    return CheckResult(rule_id=None, title=title, status=status, detail=detail, sources=[Source(pdf=pdf, page=page)])


RESULTS = [
    r("pass", "Required files"),
    r("pass", "Written in C"),
    r("fail", "Makefile rules", "Makefile is missing: fclean, re."),
    r("skipped", "Passes norminette", "norminette is not installed in the sandbox."),
    r("manual", "Needs manual review", "The program must display the shortest sequence of instructions.", page=7),
    r("manual", "Needs manual review", "Your program must not leak memory.", page=8),
    r("manual", "Needs manual review", "The program must display the shortest sequence of instructions.", pdf="other.pdf", page=2),  # duplicate wording
]


def build(results=RESULTS, **kw):
    return build_review_prompt(project="push_swap", subjects=["push_swap.pdf"], lang="c", results=results, **{"report_dir": REPORT_DIR, **kw})


def fix(results, **kw):
    return build_fix_prompt(project="push_swap", subjects=["push_swap.pdf"], lang="c", results=results, **{"report_dir": REPORT_DIR, **kw})


def manual(rule_id, detail):
    return CheckResult(rule_id=rule_id, title="Needs manual review", status="manual", detail=detail,
                       sources=[Source(pdf="push_swap.pdf", page=7)])
