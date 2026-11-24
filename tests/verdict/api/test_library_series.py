"""A series has a folder of its own in the library (samples/common-core/cpp-modules/cpp00.pdf, like cpp-modules/ in the projects folder)."""

from tests.conftest import SUBJECT_PAGES, make_pdf


def file_series(harness, track="common-core", series="cpp-modules", name="cpp00.pdf", data=None):
    folder = harness.settings.samples / track / series
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data or make_pdf(SUBJECT_PAGES))
    return folder / name


def test_the_listing_finds_the_pdfs_of_a_series_with_their_folder_in_the_path(client):
    c, harness = client
    file_series(harness)
    items = {i["path"]: i for i in c.get("/api/library").json()["items"]}
    assert set(items) == {"common-core/push_swap.pdf", "common-core/cpp-modules/cpp00.pdf"}
    assert items["common-core/cpp-modules/cpp00.pdf"]["name"] == "cpp00.pdf" and items["common-core/cpp-modules/cpp00.pdf"]["track"] == "common-core"


def test_a_pdf_of_a_series_is_added_to_a_review_like_any_other(client):
    c, harness = client
    file_series(harness)
    sid = c.post("/api/sessions").json()["id"]
    answer = c.post(f"/api/sessions/{sid}/subjects", json={"paths": ["common-core/cpp-modules/cpp00.pdf"]})
    assert answer.status_code == 200
    assert [(s["name"], s["track"]) for s in answer.json()["subjects"] if s["kind"] == "subject"] == [("cpp00.pdf", "common-core")]


def test_a_review_finds_the_library_copy_of_a_subject_that_is_filed_in_a_series_folder(client):
    c, harness = client
    pdf = file_series(harness)
    sid = c.post("/api/sessions").json()["id"]
    c.post(f"/api/sessions/{sid}/subjects", json={"paths": ["common-core/cpp-modules/cpp00.pdf"]})
    session = harness.store.get(sid)
    harness.files.directory(session).joinpath("cpp00.pdf").unlink()           # its own copy is gone: the library's is found, wherever it is filed
    assert harness.files.pdf(session, "cpp00.pdf") == pdf


def test_uploading_a_pdf_that_is_already_filed_in_a_series_makes_no_second_copy(client):
    c, harness = client
    data = make_pdf(SUBJECT_PAGES)
    file_series(harness, data=data)
    answer = c.post("/api/library/common-core/subjects", files=[("files", ("cpp00.pdf", data, "application/pdf"))])
    assert answer.status_code == 201 and answer.json()["items"][0]["path"] == "common-core/cpp-modules/cpp00.pdf"
    assert not (harness.settings.samples / "common-core" / "cpp00.pdf").exists()


def test_a_different_file_with_the_name_of_one_in_a_series_is_not_let_in(client):
    c, harness = client
    file_series(harness)
    other = make_pdf(SUBJECT_PAGES[:1])
    answer = c.post("/api/library/common-core/subjects", files=[("files", ("cpp00.pdf", other, "application/pdf"))])
    assert answer.status_code == 409 and "cpp-modules/cpp00.pdf" in answer.json()["detail"]


def test_what_is_hidden_or_a_link_inside_a_series_folder_is_not_listed(client, tmp_path):
    c, harness = client
    folder = file_series(harness).parent
    (folder / ".hidden.pdf").write_bytes(make_pdf(SUBJECT_PAGES))
    (folder / "link.pdf").symlink_to(tmp_path / "outside.pdf")
    (harness.settings.samples / "rncp").mkdir()
    (harness.settings.samples / "rncp" / "linked").symlink_to(folder, target_is_directory=True)
    paths = [i["path"] for i in c.get("/api/library").json()["items"]]
    assert paths == ["common-core/push_swap.pdf", "common-core/cpp-modules/cpp00.pdf"] or sorted(paths) == sorted(
        ["common-core/push_swap.pdf", "common-core/cpp-modules/cpp00.pdf"])
