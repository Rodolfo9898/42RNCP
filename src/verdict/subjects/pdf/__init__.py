"""Reading and showing the pages of a subject PDF."""

from verdict.subjects.pdf.reader import read_pages
from verdict.subjects.pdf.renderer import render_page

__all__ = ["read_pages", "render_page"]
