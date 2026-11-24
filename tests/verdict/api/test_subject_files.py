"""The PDFs of a review on disk (workspace/<session>/subjects/): what the sandbox reads as $SUBJECTS_DIR, kept in step with the session."""

import pytest

from tests.verdict.api.support import NORM, new_session, prepared_session
from verdict.core.errors import NotFound


def test_the_review_folder_holds_the_chosen_subjects_and_the_norm_only_while_c_is_detected(client):
    c, harness = client
    sid, repo = prepared_session(c, harness, "pdfs1")                              # push_swap.pdf from the library, main.c in the project
    session = harness.store.get(sid)
    harness.norm.sync(session)                                                     # C is detected: the Norm applies
    folder = harness.files.sync(session)
    assert folder == harness.settings.workspace / sid / "subjects"
    assert sorted(p.name for p in folder.iterdir()) == ["en.norm.pdf", "push_swap.pdf"]
    assert (folder / "en.norm.pdf").read_bytes() == (harness.settings.samples / "en.norm.pdf").read_bytes()
    assert (folder / "en.norm.pdf").stat().st_mode & 0o777 == 0o444 and (folder / "push_swap.pdf").read_bytes()[:4] == b"%PDF"
    del session.subjects[NORM]                                                     # the Norm no longer applies (sync does this when C goes away)
    assert sorted(p.name for p in harness.files.sync(session).iterdir()) == ["push_swap.pdf"]
    assert c.delete(f"/api/sessions/{sid}/subjects/push_swap.pdf").status_code == 200
    # the subject is gone from the folder; the Norm is back because, with no subject naming a language, main.c is what says "C"
    assert [p.name for p in harness.files.sync(harness.store.get(sid)).iterdir()] == ["en.norm.pdf"]


def test_the_folder_is_rebuilt_for_an_older_session_and_repairs_itself(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs2")
    session = harness.store.get(sid)
    folder = harness.files.sync(session)
    (folder / "push_swap.pdf").chmod(0o644)
    (folder / "push_swap.pdf").unlink()                                            # lost (an old session, or something deleted it)
    (folder / "stale.pdf").write_bytes(b"%PDF-1.4 left over")
    (folder / "notes.txt").write_text("not a pdf: left alone")
    harness.files.sync(session)
    assert sorted(p.name for p in folder.iterdir()) == ["en.norm.pdf", "notes.txt", "push_swap.pdf"]        # (a C subject brings the Norm)
    assert (folder / "push_swap.pdf").read_bytes()[:4] == b"%PDF"


def test_a_subject_whose_pdf_is_gone_everywhere_is_left_out_without_failing(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs2b")
    session = harness.store.get(sid)
    folder = harness.files.sync(session)
    (folder / "push_swap.pdf").chmod(0o644)
    (folder / "push_swap.pdf").unlink()
    (harness.settings.samples / "common-core" / "push_swap.pdf").unlink()
    assert "push_swap.pdf" not in [p.name for p in harness.files.sync(session).iterdir()] and "push_swap.pdf" in session.subjects


def test_a_copy_that_is_a_link_is_never_read_or_removed(client, tmp_path):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs2c")
    session = harness.store.get(sid)
    folder = harness.files.sync(session)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4 elsewhere")
    (folder / "linked.pdf").symlink_to(outside)
    harness.files.sync(session)
    assert (folder / "linked.pdf").is_symlink() and outside.exists()                # (not ours: left as it is)
    with pytest.raises(NotFound):
        harness.files.pdf(session, "linked.pdf")


def test_the_pdf_of_a_subject_is_its_own_copy_then_the_librarys(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs2d")
    session = harness.store.get(sid)
    own = harness.files.directory(session) / "push_swap.pdf"
    assert harness.files.pdf(session, "push_swap.pdf") == own
    own.unlink()
    assert harness.files.pdf(session, "push_swap.pdf") == harness.settings.samples / "common-core" / "push_swap.pdf"
    with pytest.raises(NotFound, match="is not a subject of this session"):
        harness.files.pdf(session, "other.pdf")


def test_removing_a_subject_removes_only_a_file_named_like_it(client):
    c, harness = client
    sid = new_session(c)
    session = harness.store.get(sid)
    harness.files.keep(session, "a.pdf", b"%PDF-a")
    harness.files.keep(session, "b.pdf", b"%PDF-b")
    harness.files.drop(session, "../../a.pdf")                                      # (only the name counts, never a path)
    assert sorted(p.name for p in harness.files.directory(session).iterdir()) == ["b.pdf"]
