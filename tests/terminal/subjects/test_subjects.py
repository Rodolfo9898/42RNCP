"""src/terminal/subjects: the PDFs of a review (subjects, and the Norm when it applies), handed over by the web app."""

import hashlib
import os
import time
from dataclasses import replace

from fastapi.testclient import TestClient

from terminal.api.app import create_app
from terminal.report.files import ReportFiles
from terminal.settings.limits import Limits
from tests.terminal.fakes import HEADERS

PDF_A = b"%PDF-1.4\n% subject a\n"
PDF_B = b"%PDF-1.4\n% the norm\n"


def put_pdfs(client, files, sid="sess-pdf001", headers=HEADERS):
    return client.put(f"/sessions/{sid}/subjects", headers=headers, files=[("files", (name, data, "application/pdf")) for name, data in files])


def held(client, sid="sess-pdf001"):
    return client.get(f"/sessions/{sid}/subjects", headers=HEADERS).json()


def limited(world, display, **limits):
    return TestClient(create_app(replace(world.settings, limits=Limits(**limits)), display))


def test_pdfs_are_stored_listed_by_hash_and_replaced_as_a_set(world, client):
    assert held(client) == {"files": {}}
    r = put_pdfs(client, [("libft.pdf", PDF_A), ("en.norm.pdf", PDF_B)])
    assert r.status_code == 200 and r.json() == {"stored": ["en.norm.pdf", "libft.pdf"]}
    assert held(client) == {"files": {"en.norm.pdf": hashlib.sha256(PDF_B).hexdigest(), "libft.pdf": hashlib.sha256(PDF_A).hexdigest()}}
    folder = world.subjects / "sess-pdf001"
    assert (folder / "libft.pdf").read_bytes() == PDF_A and (folder / "libft.pdf").stat().st_mode & 0o777 == 0o444     # read-only
    put_pdfs(client, [("nm.pdf", PDF_A)])                                                                              # a new set replaces the old
    assert sorted(p.name for p in folder.iterdir()) == ["nm.pdf"]
    assert not [p for p in world.subjects.iterdir() if p.name.startswith((".incoming", ".old"))]                       # no scraps left


def test_only_files_that_are_pdfs_by_name_are_listed(world, client):
    put_pdfs(client, [("libft.pdf", PDF_A)])
    folder = world.subjects / "sess-pdf001"
    (folder / "notes.txt").write_text("not a subject")
    (folder / "link.pdf").symlink_to(world.secret)
    assert list(held(client)["files"]) == ["libft.pdf"]


def test_the_session_must_be_a_session_id(world, client):
    for sid in ("abc", "x" * 40, "a.b.c.d.e"):
        assert put_pdfs(client, [("a.pdf", PDF_A)], sid=sid).status_code == 400, sid
    for sid in ("a/b", "../etc"):                                                      # (these cannot even name a review: no such route)
        assert put_pdfs(client, [("a.pdf", PDF_A)], sid=sid).status_code == 404, sid
    assert held(client, "abc") == {"files": {}} and held(client, "x" * 40) == {"files": {}}
    assert not world.subjects.exists() or not any(world.subjects.iterdir())


def test_only_real_pdfs_with_plain_names_are_accepted_and_a_refusal_changes_nothing(world, client):
    put_pdfs(client, [("keep.pdf", PDF_A)])
    folder = world.subjects / "sess-pdf001"
    for files in ([("../x.pdf", PDF_A)], [("a/b.pdf", PDF_A)], [(".hidden.pdf", PDF_A)], [("notes.txt", PDF_A)],
                  [("fake.pdf", b"<html>not a pdf</html>")], [("a.pdf", PDF_A), ("a.pdf", PDF_A)], [("ok.pdf", PDF_A), ("bad.exe", PDF_A)]):
        assert put_pdfs(client, files).status_code == 400, files
    assert sorted(p.name for p in folder.iterdir()) == ["keep.pdf"]                                                    # the earlier set survived


def test_the_handover_is_limited_in_count_size_and_total(world, display):
    put_pdfs(limited(world, display), [("keep.pdf", PDF_A)])
    folder = world.subjects / "sess-pdf001"
    assert put_pdfs(limited(world, display, max_subject_files=1), [("a.pdf", PDF_A), ("b.pdf", PDF_A)]).status_code == 400
    assert put_pdfs(limited(world, display, max_subject_file_bytes=10), [("big.pdf", PDF_A)]).status_code == 400
    assert put_pdfs(limited(world, display, max_subject_total_bytes=30), [("a.pdf", PDF_A), ("b.pdf", PDF_A)]).status_code == 400
    assert sorted(p.name for p in folder.iterdir()) == ["keep.pdf"]
    assert put_pdfs(limited(world, display, max_subject_files=1), [("a.pdf", PDF_A)]).status_code == 200                # one is within the limit


def test_a_store_that_cannot_write_is_a_500_that_says_why(world, client):
    world.subjects.parent.mkdir(exist_ok=True)
    world.subjects.write_text("a file where the folder should be")
    r = put_pdfs(client, [("a.pdf", PDF_A)])
    assert r.status_code == 500 and "could not store the PDFs" in r.json()["detail"]


def age(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_folders_nobody_uses_are_pruned_but_one_claude_was_started_for_is_kept(world, client):
    put_pdfs(client, [("a.pdf", PDF_A)], sid="sess-old001")
    put_pdfs(client, [("a.pdf", PDF_A)], sid="sess-old002")
    for sid in ("sess-old001", "sess-old002"):
        age(world.subjects / sid, world.settings.limits.stale_subjects_seconds + 60)
    ReportFiles(world.settings.folders).prepare("sess-old002")                         # claude was started in the editor for this one
    put_pdfs(client, [("a.pdf", PDF_A)], sid="sess-new001")                            # any new handover prunes
    assert not (world.subjects / "sess-old001").exists()
    assert (world.subjects / "sess-old002").is_dir() and (world.subjects / "sess-new001").is_dir()


def test_a_recent_folder_is_not_pruned(world, client):
    put_pdfs(client, [("a.pdf", PDF_A)], sid="sess-new002")
    put_pdfs(client, [("a.pdf", PDF_A)], sid="sess-new003")
    assert (world.subjects / "sess-new002").is_dir()


def test_what_an_interrupted_handover_left_is_not_taken_for_a_review(world, client):
    put_pdfs(client, [("a.pdf", PDF_A)])
    (world.subjects / ".incoming-abc").mkdir()
    (world.subjects / ".incoming-abc" / "x.pdf").write_bytes(PDF_A)
    put_pdfs(client, [("a.pdf", PDF_A)], sid="sess-pdf009")
    assert (world.subjects / ".incoming-abc").is_dir(), "a handover under way is not stale"
    assert held(client, ".incoming-abc") == {"files": {}}
