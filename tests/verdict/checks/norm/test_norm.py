import shutil

import pytest

from verdict.checks.norm import checkers
from verdict.checks.norm.checkers import NormChecker
from verdict.checks.norm.report import NormReport
from verdict.core.models import Rule, Source

from tests.verdict.checks.helpers import MLX, answer, by_title, project, review


@pytest.mark.skipif(shutil.which("norminette") is None, reason="norminette not installed")
def test_norm_and_globals_use_norminette(bad_repo, local_sandbox):
    results = review(bad_repo, local_sandbox)
    assert by_title(results, "Passes norminette").status == "fail"
    assert by_title(results, "No global variables").status == "fail"


def test_the_norm_result_says_minilibx_was_left_out(tmp_path, monkeypatch):
    repo = project(tmp_path, {**MLX, "src/main.c": "int main;\n"})
    rule = Rule(id="n", kind="norm", title="Passes norminette", sources=[Source(pdf="en.norm.pdf", page=1)])
    seen = {}

    def fake_report(c):
        seen["files"] = [p.as_posix() for p in c.source_files(".")]
        return NormReport(files=1)

    monkeypatch.setattr(checkers, "norm_report", fake_report)
    res = answer(NormChecker(), repo, rule)
    assert res.status == "pass" and "`gfx/mlx_custom/`" in res.detail and "not written by them" in res.detail
    assert seen["files"] == ["src/main.c"]
