"""terminal/readpdf: the command claude uses to read the subject PDFs instead of writing an extraction script each time."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import make_pdf

SCRIPT = Path(__file__).resolve().parent.parent / "terminal" / "readpdf"
SUBJECT = ["Chapter I\nIntroduction\nThe Norm applies here.", "Chapter II\nMandatory part\nFiles to Submit: Makefile", "Chapter III\nBonus part\nNothing about the NORM."]


@pytest.fixture
def folder(tmp_path):
    subjects = tmp_path / "subjects"
    subjects.mkdir()
    (subjects / "libft.pdf").write_bytes(make_pdf(SUBJECT))
    (subjects / "en.norm.pdf").write_bytes(make_pdf(["The Norm", "Header rules"]))
    return subjects


def readpdf(*args, folder=None, **env):
    environment = {k: v for k, v in os.environ.items() if k != "SUBJECTS_DIR"}
    if folder is not None:
        environment["SUBJECTS_DIR"] = str(folder)
    done = subprocess.run([sys.executable, str(SCRIPT), *args], env={**environment, **env}, capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout, done.stderr


def test_with_no_argument_it_lists_the_pdfs_of_the_review_and_their_pages(folder):
    code, out, _ = readpdf(folder=folder)
    assert code == 0 and out.splitlines() == ["en.norm.pdf\t2 page(s)", "libft.pdf\t3 page(s)"]
    empty = folder.parent / "empty"
    empty.mkdir()
    assert "no PDF" in readpdf(folder=empty)[1]


def test_it_prints_the_text_page_by_page_with_a_header_per_page(folder):
    code, out, _ = readpdf("libft.pdf", folder=folder)
    assert code == 0
    assert "=== libft.pdf, page 1 of 3 ===" in out and "=== libft.pdf, page 3 of 3 ===" in out
    assert "The Norm applies here." in out and "Files to Submit: Makefile" in out


def test_pages_can_be_picked_and_the_name_may_leave_out_the_extension(folder):
    _, out, _ = readpdf("libft", "2", folder=folder)
    assert "page 2 of 3" in out and "page 1 of 3" not in out and "page 3 of 3" not in out
    _, out, _ = readpdf("libft.pdf", "1,3", folder=folder)
    assert "page 1 of 3" in out and "page 2 of 3" not in out and "page 3 of 3" in out
    _, out, _ = readpdf("libft.pdf", "2-3", folder=folder)
    assert "page 2 of 3" in out and "page 3 of 3" in out and "page 1 of 3" not in out


def test_it_searches_like_grep_with_the_page_of_each_line_and_an_exit_status_that_says_whether_it_found_any(folder):
    code, out, _ = readpdf("libft.pdf", "--grep", "norm", folder=folder)
    assert code == 0 and out.splitlines() == ["libft.pdf p.1: The Norm applies here.", "libft.pdf p.3: Nothing about the NORM."]       # any case
    assert readpdf("libft.pdf", "--grep", "NORM", folder=folder)[1] == out                      # whatever case the word is typed in
    code, out, _ = readpdf("libft.pdf", "--grep", "nonexistent-word", folder=folder)
    assert code == 1 and out == ""
    assert readpdf("libft.pdf", "2", "--grep", "makefile", folder=folder)[1] == "libft.pdf p.2: Files to Submit: Makefile\n"       # within chosen pages


def test_bad_requests_say_what_is_wrong_and_print_no_traceback(folder):
    for args, message in ((("libft.pdf", "9"), "do not exist"), (("libft.pdf", "x"), "not a page list"), (("libft.pdf", "3-1"), "do not exist"),
                          (("nothing.pdf",), "no PDF called nothing.pdf"), (("libft.pdf", "1", "2"), "usage"), (("libft.pdf", "--grep"), "needs a word")):
        code, out, err = readpdf(*args, folder=folder)
        assert code == 1 and out == "" and message in err and "Traceback" not in err, args


def test_it_reads_only_the_pdfs_of_the_review(folder, tmp_path):
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(make_pdf(["secret"]))
    (folder / "link.pdf").symlink_to(outside)
    (folder / "notes.txt").write_text("not a pdf")
    (folder / "fake.pdf").write_text("%PDF-nope? no: just text")
    for target in (str(outside), "../outside.pdf", "link.pdf", "/etc/passwd", str(folder / ".." / "outside.pdf")):
        code, out, err = readpdf(target, folder=folder)
        assert code == 1 and "secret" not in out and ("not inside" in err or "no PDF called" in err), (target, err)
    assert "not a PDF" in readpdf("notes.txt", folder=folder)[2]
    assert readpdf(str(folder / "libft.pdf"), "1", folder=folder)[0] == 0                       # a path inside the folder is fine


def test_without_the_folder_it_explains_instead_of_guessing(tmp_path):
    for env_folder in (None, tmp_path / "does-not-exist"):
        code, out, err = readpdf(folder=env_folder)
        assert code == 1 and "no $SUBJECTS_DIR folder" in err and "Traceback" not in err


def test_the_help_needs_no_folder_and_nothing_is_ever_written(folder):
    before = sorted(p.name for p in folder.iterdir())
    code, out, _ = readpdf("--help")
    assert code == 0 and "readpdf libft.pdf 4-6" in out and "--grep" in out
    readpdf("libft.pdf", folder=folder)
    readpdf("libft.pdf", "--grep", "norm", folder=folder)
    assert sorted(p.name for p in folder.iterdir()) == before
