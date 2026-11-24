from verdict.checks import Ctx
from verdict.checks.runtime.smoke import NoCrashChecker, NoLeaksChecker
from verdict.core.models import Rule

from tests.verdict.checks.helpers import archive_repo, needs_build_tools


@needs_build_tools
def test_runtime_checks_skip_a_library_instead_of_running_its_objects(tmp_path, local_sandbox):
    rules = [Rule(id=kind, kind=kind, title=kind, text="", section="mandatory", sources=[]) for kind in ("no_crash", "no_leaks")]
    ctx = Ctx(repo=archive_repo(tmp_path).resolve(), rules=rules, sandbox=local_sandbox, lang="c")
    assert [r.status for r in NoCrashChecker().run(ctx, rules[0])] == ["skipped"]
    assert [r.status for r in NoLeaksChecker().run(ctx, rules[1])] == ["skipped"]
