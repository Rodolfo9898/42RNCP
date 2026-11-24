"""A better parser reaches reviews that already had the subject: the rules are read again at the next run."""

import shutil

import pytest

from tests.verdict.api.support import attach_repo, new_session, prepared_session, run_to_completion
from tests.paths import SAMPLES

REAL_FT_PRINTF = SAMPLES / "common-core" / "ft_printf.pdf"
OLD_FT_PRINTF_FILES = [["Makefile"], ["*.h"], ["*/*.h"], ["*.c"], ["*/*.c"]]          # how it was parsed before `*.c` and `*/*.c` became one requirement
CURRENT_FILES = [["Makefile"], ["*.h", "*/*.h"], ["*.c", "*/*.c"]]


def ft_printf_session(c, harness, name):
    if not REAL_FT_PRINTF.is_file():
        pytest.skip("the library PDF is not here")
    (harness.settings.samples / "common-core").mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_FT_PRINTF, harness.settings.samples / "common-core" / "ft_printf.pdf")
    sid = new_session(c)
    assert c.post(f"/api/sessions/{sid}/subjects", json={"paths": ["common-core/ft_printf.pdf"]}).status_code == 200
    repo = attach_repo(harness, sid, name)
    for file in ("Makefile", "ft_printf.h", "ft_printf.c"):                                # everything at the root, as the subject allows
        (repo / file).write_text("x\n")
    return sid, repo


def required_files_rule(harness, sid):
    return next(r for r in harness.store.get(sid).subjects["ft_printf.pdf"].rules if r.kind == "required_files")


def go_back_to_the_old_rules(harness, sid):
    """What a session made before the parser improved has stored for the subject."""
    required_files_rule(harness, sid).params["files"] = [list(entry) for entry in OLD_FT_PRINTF_FILES]


def test_a_session_that_stored_the_old_rules_gets_the_fixed_ones_at_the_next_run(client):
    c, harness = client
    sid, _ = ft_printf_session(c, harness, "ftp1")
    assert required_files_rule(harness, sid).params["files"] == CURRENT_FILES
    go_back_to_the_old_rules(harness, sid)
    state = run_to_completion(c, sid)
    found = next(r for r in state["results"] if r["title"].startswith("Required files"))
    assert found["status"] == "pass" and "Missing" not in found["detail"]                   # the screenshot: "Missing: */*.h, */*.c"
    assert required_files_rule(harness, sid).params["files"] == CURRENT_FILES              # and the session now keeps the current rules


def test_refreshing_the_rules_changes_nothing_when_nothing_changed_and_keeps_rules_it_cannot_reread(client):
    c, harness = client
    sid, _ = ft_printf_session(c, harness, "ftp2")
    session = harness.store.get(sid)
    harness.norm.sync(session)
    assert harness.subjects.refresh_rules(session) is False                                # nothing to update: the same rules come out
    go_back_to_the_old_rules(harness, sid)
    assert harness.subjects.refresh_rules(session) is True and harness.subjects.refresh_rules(session) is False
    old = session.subjects["ft_printf.pdf"].model_copy(deep=True)
    for path in (harness.files.directory(session) / "ft_printf.pdf", harness.settings.samples / "common-core" / "ft_printf.pdf"):
        path.chmod(0o644)
        path.unlink()                                                                       # the PDF is gone from everywhere
    assert harness.subjects.refresh_rules(session) is False and session.subjects["ft_printf.pdf"] == old       # so the rules it has stay


def test_a_pdf_that_can_no_longer_be_parsed_keeps_the_rules_the_session_has(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "ftp3")
    session = harness.store.get(sid)
    before = session.subjects["push_swap.pdf"].model_copy(deep=True)
    (harness.files.directory(session) / "push_swap.pdf").chmod(0o644)
    (harness.files.directory(session) / "push_swap.pdf").write_bytes(b"%PDF-1.4 damaged")
    assert harness.subjects.refresh_rules(session) is False and session.subjects["push_swap.pdf"] == before
