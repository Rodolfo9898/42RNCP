"""src/terminal/report: the report claude saves, read as data."""

import pytest

from terminal.report.files import REVIEW_FILE, ReportFiles
from terminal.report.reader import ReportReader
from terminal.settings.limits import Limits

NOTHING = {"found": False, "text": "", "name": "claude-review.md"}


def save(world, sid, text):
    folder = ReportFiles(world.settings.folders).prepare(sid)
    (folder / REVIEW_FILE).write_text(text)
    return folder / REVIEW_FILE


def reader_for(world, **limits):
    files = ReportFiles(world.settings.folders)
    return ReportReader(files, Limits(**limits) if limits else world.settings.limits)


def test_the_saved_report_of_a_review_is_returned(world):
    save(world, "sess-abc123", "# Report\n\n## Verdict\nready to pass\n")
    got = reader_for(world).read("sess-abc123")
    assert got["found"] and "ready to pass" in got["text"] and got["name"] == "claude-review.md"
    assert reader_for(world).read("another-session") == NOTHING


def test_nothing_saved_is_not_found_and_an_empty_report_is_nothing(world):
    assert reader_for(world).read("sess-abc123") == NOTHING
    save(world, "sess-abc123", "  \n\n")
    assert reader_for(world).read("sess-abc123") == NOTHING


@pytest.mark.parametrize("sid", ["", "a", "../../etc", "a/b", "x" * 40])
def test_a_malformed_session_id_reads_nothing(world, sid):
    assert reader_for(world).read(sid) == NOTHING


def test_a_link_or_a_huge_file_is_never_returned(world):
    saved = save(world, "s-12345", "fine")
    saved.unlink()
    saved.symlink_to(world.secret)
    assert reader_for(world).read("s-12345")["found"] is False
    saved.unlink()
    saved.write_text("far too long for the limit")
    assert reader_for(world, max_review_bytes=5).read("s-12345")["found"] is False
    assert reader_for(world).read("s-12345")["found"] is True


def test_the_report_is_kept_outside_the_project(world):
    folder = ReportFiles(world.settings.folders).prepare("sess-liv007")
    assert folder == world.reports / "sess-liv007" and folder.is_dir() and not folder.is_relative_to(world.projects)
    (world.repo / "claude-review.md").write_text("inside the project")                 # a file of the project is never taken for the report
    assert reader_for(world).read("sess-liv007") == NOTHING


def test_a_new_pass_starts_without_the_report_of_the_last_one(world):
    files = ReportFiles(world.settings.folders)
    old = save(world, "abcdef123", "# the report of the last pass")
    (old.parent / "notes.txt").write_text("not a report")
    assert files.discard("abcdef123") is True
    assert not old.exists() and (old.parent / "notes.txt").exists(), "only the report goes"
    assert files.discard("abcdef123") is False, "a folder without one is fine"


def test_discarding_removes_a_link_but_never_follows_it(world):
    files = ReportFiles(world.settings.folders)
    saved = save(world, "abcdef123", "x")
    saved.unlink()
    saved.symlink_to(world.secret)
    assert files.discard("abcdef123") is True
    assert not saved.is_symlink() and world.secret.read_text() == "top secret"


@pytest.mark.parametrize("sid", ["", "a", "../../etc", "a/b", "x" * 40])
def test_nothing_is_discarded_or_prepared_for_a_malformed_session_id(world, sid):
    files = ReportFiles(world.settings.folders)
    assert files.discard(sid) is False and files.saved(sid) is None and files.started(sid) is False
    with pytest.raises(ValueError):
        files.prepare(sid)


def test_a_review_has_started_once_its_report_folder_exists(world):
    files = ReportFiles(world.settings.folders)
    assert files.started("abcdef123") is False
    files.prepare("abcdef123")
    assert files.started("abcdef123") is True and (world.reports / "abcdef123").is_dir()
