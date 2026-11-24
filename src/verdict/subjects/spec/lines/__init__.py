"""Turning the pages of a subject into lines that know their chapter and part."""

from verdict.subjects.spec.lines.contents import is_toc_page
from verdict.subjects.spec.lines.reader import LineReader, read_lines

__all__ = ["LineReader", "is_toc_page", "read_lines"]
