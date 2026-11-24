"""The subjects of a review: library PDFs added to it and taken away, their rules, and their pages as images."""

import pytest

from tests.conftest import SUBJECT_PAGES, make_pdf
from tests.verdict.api.support import NORM, a_result, new_session
from verdict.library import pages
from verdict.library.pages import render_page


def add(c, sid, *paths):
    return c.post(f"/api/sessions/{sid}/subjects", json={"paths": list(paths)})


def names(view, kind="subject"):
    return [s["name"] for s in view["subjects"] if s["kind"] == kind]


def test_a_library_pdf_is_added_with_its_rules_and_track(client):
    c, _ = client
    sid = new_session(c)
    r = add(c, sid, "common-core/push_swap.pdf")
    assert r.status_code == 200
    subject = r.json()["subjects"][0]
    assert subject["name"] == "push_swap.pdf" and subject["track"] == "common-core" and subject["rules"] and subject["lang"] == "c"
    assert subject["pages"] == len(SUBJECT_PAGES)
    assert c.get(f"/api/sessions/{sid}").json()["subjects"] == r.json()["subjects"]


def test_what_is_not_in_the_library_is_not_found(client):
    c, _ = client
    sid = new_session(c)
    for bad in ("../secret.pdf", "push_swap.pdf", "rncp/push_swap.pdf", "en.norm.pdf", "common-core/../en.norm.pdf", ""):
        assert add(c, sid, bad).status_code == 404, bad
    missing = add(c, sid, "common-core/push_swap.pdf", "rncp/nope.pdf")
    assert missing.status_code == 404 and missing.json()["detail"] == "rncp/nope.pdf is not in the library"


def test_several_uploaded_pdfs_are_added_and_their_rules_merged(client):
    c, _ = client
    sid = new_session(c)
    for name in ("a.pdf", "b.pdf"):
        assert c.post("/api/library/rncp/subjects", files=[("files", (name, make_pdf(SUBJECT_PAGES), "application/pdf"))]).status_code == 201
    r = add(c, sid, "rncp/a.pdf", "rncp/b.pdf")
    assert r.status_code == 200 and names(r.json()) == ["a.pdf", "b.pdf"]
    assert {s["track"] for s in r.json()["subjects"] if s["kind"] == "subject"} == {"rncp"}
    assert all(s["rules"] for s in r.json()["subjects"])


def test_an_uploaded_subject_can_be_chosen_in_the_track_it_was_uploaded_to(client):
    c, _ = client
    sid = new_session(c)
    c.post("/api/library/post-common-core/subjects", files=[("files", ("ft_ls.pdf", make_pdf(SUBJECT_PAGES), "application/pdf"))])
    assert "post-common-core/ft_ls.pdf" in [i["path"] for i in c.get("/api/library").json()["items"]]
    subject = next(s for s in add(c, sid, "post-common-core/ft_ls.pdf").json()["subjects"] if s["name"] == "ft_ls.pdf")
    assert subject["track"] == "post-common-core"


def test_the_same_subject_added_twice_is_one_subject(client):
    c, _ = client
    sid = new_session(c)
    add(c, sid, "common-core/push_swap.pdf")
    assert names(add(c, sid, "common-core/push_swap.pdf").json()) == ["push_swap.pdf"]


def test_a_review_has_at_most_twenty_subjects(client):
    c, harness = client
    sid = new_session(c)
    tiny = make_pdf(["Chapter I\nMandatory part\nYou must write a configuration file.\n"])
    (harness.settings.samples / "rncp").mkdir()
    for n in range(21):
        (harness.settings.samples / "rncp" / f"s{n:02}.pdf").write_bytes(tiny)
    first = [f"rncp/s{n:02}.pdf" for n in range(20)]
    assert add(c, sid, *first).status_code == 200
    refused = add(c, sid, "rncp/s20.pdf")
    assert refused.status_code == 400 and "at most 20 subjects" in refused.json()["detail"]
    assert len(names(c.get(f"/api/sessions/{sid}").json())) == 20


def test_a_library_file_that_is_not_a_pdf_or_cannot_be_read_is_refused(client):
    c, harness = client
    sid = new_session(c)
    (harness.settings.samples / "rncp").mkdir()
    (harness.settings.samples / "rncp" / "fake.pdf").write_bytes(b"just text")
    (harness.settings.samples / "rncp" / "broken.pdf").write_bytes(b"%PDF-1.4 but nothing more")
    assert add(c, sid, "rncp/fake.pdf").json()["detail"] == "fake.pdf is not a PDF"
    broken = add(c, sid, "rncp/broken.pdf")
    assert broken.status_code == 400 and "could not read broken.pdf" in broken.json()["detail"]
    assert c.get(f"/api/sessions/{sid}").json()["subjects"] == []


def test_adding_or_removing_a_subject_forgets_the_results_of_the_run(client):
    c, harness = client
    sid = new_session(c)
    add(c, sid, "common-core/push_swap.pdf")
    session = harness.store.get(sid)
    session.results = [a_result()]
    session.state = "done"
    add(c, sid, "common-core/push_swap.pdf")
    assert session.results == [] and session.state == "idle"
    session.results = [a_result()]
    c.delete(f"/api/sessions/{sid}/subjects/push_swap.pdf")
    assert session.results == []


def test_a_subject_is_removed_with_its_copy_and_removing_an_unknown_one_changes_nothing(client):
    c, harness = client
    sid = new_session(c)
    add(c, sid, "common-core/push_swap.pdf")
    copy = harness.files.directory(harness.store.get(sid)) / "push_swap.pdf"
    assert copy.is_file()
    assert c.delete(f"/api/sessions/{sid}/subjects/other.pdf").json()["subjects"] != []
    removed = c.delete(f"/api/sessions/{sid}/subjects/push_swap.pdf")
    assert removed.status_code == 200 and removed.json()["subjects"] == [] and not copy.exists()


def test_subject_pages_are_served_as_images(client):
    c, harness = client
    sid = new_session(c)
    c.post("/api/library/rncp/subjects", files=[("files", ("ft_ls.pdf", make_pdf(SUBJECT_PAGES), "application/pdf"))])
    add(c, sid, "rncp/ft_ls.pdf")
    page = c.get(f"/api/sessions/{sid}/subjects/ft_ls.pdf/pages/1.png")
    assert page.status_code == 200 and page.headers["content-type"] == "image/png" and page.content.startswith(b"\x89PNG")
    assert page.headers["cache-control"] == "private, max-age=3600"
    assert c.get(f"/api/sessions/{sid}/subjects/ft_ls.pdf/pages/{len(SUBJECT_PAGES) + 1}.png").status_code == 404
    assert c.get(f"/api/sessions/{sid}/subjects/ft_ls.pdf/pages/0.png").status_code == 404
    assert c.get(f"/api/sessions/{sid}/subjects/{NORM}/pages/1.png").status_code == 200       # the Norm too (C subject)
    assert c.get(f"/api/sessions/{sid}/subjects/other.pdf/pages/1.png").status_code == 404
    assert c.get(f"/api/sessions/{sid}/subjects/..%2f..%2fsession.json/pages/1.png").status_code == 404
    c.delete(f"/api/sessions/{sid}/subjects/ft_ls.pdf")
    assert not (harness.files.directory(harness.store.get(sid)) / "ft_ls.pdf").exists()
    assert c.get(f"/api/sessions/{sid}/subjects/ft_ls.pdf/pages/1.png").status_code == 404


def test_subject_pages_fall_back_to_the_library_copy(client):
    c, harness = client
    sid = new_session(c)
    add(c, sid, "common-core/push_swap.pdf")
    (harness.files.directory(harness.store.get(sid)) / "push_swap.pdf").unlink()           # a session from before copies were kept
    assert c.get(f"/api/sessions/{sid}/subjects/push_swap.pdf/pages/1.png").status_code == 200
    (harness.settings.samples / "common-core" / "push_swap.pdf").unlink()
    gone = c.get(f"/api/sessions/{sid}/subjects/push_swap.pdf/pages/1.png")
    assert gone.status_code == 404 and "no longer available" in gone.json()["detail"]


def test_a_page_is_rendered_once_per_version_of_the_file(client, monkeypatch):
    c, harness = client
    sid = new_session(c)
    add(c, sid, "common-core/push_swap.pdf")
    rendered = []
    monkeypatch.setattr(pages, "render_page", lambda path, page: rendered.append(page) or render_page(path, page))
    for _ in range(2):
        assert c.get(f"/api/sessions/{sid}/subjects/push_swap.pdf/pages/1.png").status_code == 200
    assert rendered == [1]
    assert c.get(f"/api/sessions/{sid}/subjects/push_swap.pdf/pages/2.png").status_code == 200 and rendered == [1, 2]


@pytest.mark.parametrize("body", [{}, {"paths": "common-core/push_swap.pdf"}, {"path": "x"}])
def test_a_malformed_pick_is_refused_before_anything_happens(client, body):
    c, _ = client
    sid = new_session(c)
    assert c.post(f"/api/sessions/{sid}/subjects", json=body).status_code == 422
