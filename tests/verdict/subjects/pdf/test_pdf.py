import pytest

from tests.conftest import make_pdf
from verdict.subjects.pdf import read_pages, render_page


def test_the_text_of_each_page_is_read_from_bytes_or_from_a_file(tmp_path):
    data = make_pdf(["first page text", "second page text"])
    pages = read_pages(data)
    assert len(pages) == 2 and "first page text" in pages[0] and "second page text" in pages[1]
    path = tmp_path / "subject.pdf"
    path.write_bytes(data)
    assert read_pages(path) == pages


def test_a_page_is_rendered_as_a_png_and_a_page_that_does_not_exist_is_refused(tmp_path):
    path = tmp_path / "subject.pdf"
    path.write_bytes(make_pdf(["only page"]))
    assert render_page(path, 1).startswith(b"\x89PNG")
    assert len(render_page(path, 1, zoom=1.0)) < len(render_page(path, 1, zoom=3.0))
    for missing in (0, 2):
        with pytest.raises(IndexError):
            render_page(path, missing)
