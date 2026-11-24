"""The subject library: the PDFs in samples/<track>/, listed, and uploaded into the folder of their track."""

from tests.conftest import SUBJECT_PAGES, make_pdf
from verdict.library.catalog import MAX_PDF_BYTES


def upload(c, track, name, data):
    return c.post(f"/api/library/{track}/subjects", files=[("files", (name, data, "application/pdf"))])


def test_the_library_lists_its_tracks_and_subjects_but_not_the_norm(client):
    c, harness = client
    lib = c.get("/api/library").json()
    assert [t["id"] for t in lib["tracks"]] == ["common-core", "post-common-core", "rncp"]
    assert [t["label"] for t in lib["tracks"]] == ["Common Core", "Post Common Core", "RNCP"]
    size = (harness.settings.samples / "common-core" / "push_swap.pdf").stat().st_size
    assert lib["items"] == [{"path": "common-core/push_swap.pdf", "name": "push_swap.pdf", "track": "common-core", "size": size}]
    assert lib["norm"] is True                                                  # the Norm is never listed as a subject


def test_the_listing_skips_what_is_not_a_plain_pdf_of_a_known_track(client, tmp_path):
    c, harness = client
    track = harness.settings.samples / "rncp"
    track.mkdir()
    (track / "real.pdf").write_bytes(make_pdf(SUBJECT_PAGES))
    (track / "link.pdf").symlink_to(tmp_path / "outside.pdf")
    (track / "notes.txt").write_text("not a subject")
    (harness.settings.samples / "elsewhere").mkdir()
    (harness.settings.samples / "elsewhere" / "stray.pdf").write_bytes(make_pdf(SUBJECT_PAGES))
    assert [i["path"] for i in c.get("/api/library").json()["items"]] == ["common-core/push_swap.pdf", "rncp/real.pdf"]
    (harness.settings.samples / "en.norm.pdf").unlink()
    assert c.get("/api/library").json()["norm"] is False


def test_an_upload_lands_in_the_folder_of_its_track_and_is_listed(client):
    c, harness = client
    pdf = make_pdf(SUBJECT_PAGES)
    r = upload(c, "post-common-core", "ft_ls.pdf", pdf)
    assert r.status_code == 201
    item = r.json()["items"][0]
    assert item == {"path": "post-common-core/ft_ls.pdf", "name": "ft_ls.pdf", "track": "post-common-core", "size": len(pdf)}
    assert (harness.settings.samples / "post-common-core" / "ft_ls.pdf").read_bytes() == pdf
    assert item in c.get("/api/library").json()["items"]
    assert not list((harness.settings.samples / "post-common-core").glob(".*"))          # no temporary file is left behind


def test_several_pdfs_go_up_in_one_request(client):
    c, harness = client
    files = [("files", (name, make_pdf(SUBJECT_PAGES), "application/pdf")) for name in ("a.pdf", "b.pdf")]
    r = c.post("/api/library/rncp/subjects", files=files)
    assert r.status_code == 201 and [i["path"] for i in r.json()["items"]] == ["rncp/a.pdf", "rncp/b.pdf"]
    assert sorted(p.name for p in (harness.settings.samples / "rncp").iterdir()) == ["a.pdf", "b.pdf"]


def test_an_upload_into_an_unknown_track_is_refused_and_writes_nothing(client):
    c, harness = client
    pdf = make_pdf(SUBJECT_PAGES)
    refused = upload(c, "elsewhere", "ft_ls.pdf", pdf)
    assert refused.status_code == 400 and "Common Core" in refused.json()["detail"]
    assert upload(c, "..%2fetc", "ft_ls.pdf", pdf).status_code in (400, 404)
    assert c.post("/api/library/rncp/subjects").status_code == 422                       # nothing to keep
    assert sorted(p.name for p in harness.settings.samples.iterdir()) == ["common-core", "en.norm.pdf"]
    assert not (harness.settings.samples.parent / "etc").exists()


def test_what_is_not_a_pdf_or_is_the_norm_is_refused(client):
    c, harness = client
    bad = upload(c, "rncp", "x.pdf", b"not a pdf")
    assert bad.status_code == 400 and bad.json()["detail"] == "x.pdf is not a PDF"
    norm = upload(c, "rncp", "en.norm.pdf", make_pdf(SUBJECT_PAGES))                      # the Norm is not a subject
    assert norm.status_code == 400 and "is the Norm" in norm.json()["detail"]
    assert not (harness.settings.samples / "rncp").exists()


def test_an_odd_file_name_is_made_safe_before_it_is_kept(client):
    c, harness = client
    r = upload(c, "rncp", "../../etc/<b>x.pdf", make_pdf(SUBJECT_PAGES))
    assert r.status_code == 201 and r.json()["items"][0]["name"] == "_b_x.pdf"
    assert [p.name for p in (harness.settings.samples / "rncp").iterdir()] == ["_b_x.pdf"]
    assert upload(c, "rncp", "..", make_pdf(SUBJECT_PAGES)).json()["items"][0]["name"] == "subject.pdf"


def test_a_file_that_is_already_there_is_never_replaced(client):
    c, harness = client
    pdf = make_pdf(SUBJECT_PAGES)
    assert upload(c, "post-common-core", "ft_ls.pdf", pdf).status_code == 201
    assert upload(c, "post-common-core", "ft_ls.pdf", pdf).status_code == 201           # the same file again is fine
    other = make_pdf(SUBJECT_PAGES + ["Chapter III\nBonus part\nMore.\n"])
    refused = upload(c, "post-common-core", "ft_ls.pdf", other)
    assert refused.status_code == 409 and "already exists with different content" in refused.json()["detail"]
    assert (harness.settings.samples / "post-common-core" / "ft_ls.pdf").read_bytes() == pdf


def test_an_upload_never_writes_through_a_link(client, tmp_path):
    c, harness = client
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-keep me")
    (harness.settings.samples / "rncp").mkdir()
    (harness.settings.samples / "rncp" / "ft_ls.pdf").symlink_to(outside)
    refused = upload(c, "rncp", "ft_ls.pdf", make_pdf(SUBJECT_PAGES))
    assert refused.status_code == 409 and "is a link" in refused.json()["detail"] and outside.read_bytes() == b"%PDF-keep me"


def test_a_pdf_over_the_limit_is_refused(client):
    c, harness = client
    refused = upload(c, "rncp", "big.pdf", b"%PDF" + b"0" * MAX_PDF_BYTES)
    assert refused.status_code == 413 and "30 MB" in refused.json()["detail"]
    assert not (harness.settings.samples / "rncp").exists()

