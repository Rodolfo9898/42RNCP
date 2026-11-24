"""Files named by a list or a listing of the layout the subject expects, outside any table."""

from __future__ import annotations

import re

from verdict.subjects.spec.files.sentences import is_file_token
from verdict.subjects.spec.model import Line

_LIST_INTRO = re.compile(r"files (?:are|is) (?:mandatory|required)\b|^required files$", re.I)
_LS_ENTRY = re.compile(r"^([-dl])[rwxsStT-]{9}(?:\s+\S+){7}\s+(\S.*)$")
_LS_HEADER = re.compile(r"^(\.|\./[\w./\-]*):$")


def listed_files(lines: list[Line]) -> list[tuple[str, Line]]:
    """Top-level bullets of a list that the subject introduces as its mandatory files ("Required Files"), up to the next
    heading ("Optional but Recommended" is never read)."""
    out: list[tuple[str, Line]] = []
    i = 0
    while i < len(lines):
        if not _LIST_INTRO.search(lines[i].text):
            i += 1
            continue
        seen, j = 0, i + 1
        while j < len(lines):
            text = lines[j].text
            if seen and (re.fullmatch(r"[IVXLC]+(?:\.\d+)*", text) or re.match(r"(optional|recommended)\b", text, re.I)):
                break
            if text.startswith("•"):
                m = re.match(r"•\s*([^\s:—–]+)", text)
                token = m.group(1).rstrip(":,;") if m else ""
                if is_file_token(token):
                    out.append((token, lines[j]))
                seen += 1
            j += 1
        i = max(j, i + 1)
    return out


class LayoutListing:
    """One `$> ls` listing of the expected layout, read entry by entry: `ls -alR` (every file and folder two levels deep), or a plain
    `ls` of names, where [bracketed] ones are optional."""

    def __init__(self, lines: list[Line], start: int, example: bool) -> None:
        self.lines, self.start, self.example = lines, start, example
        self.recursive = "-R" in lines[start].text
        self.folder = ""
        self.found: list[tuple[str, Line, bool]] = []

    def read(self) -> list[tuple[str, Line, bool]]:
        for line in self.lines[self.start + 1:]:
            if not self._entry(line):
                break
        return self.found

    def _entry(self, line: Line) -> bool:
        """Takes the line into the listing; False when it is not part of it."""
        text = line.text
        header, entry = _LS_HEADER.match(text), _LS_ENTRY.match(text)
        if header:
            self.folder = "" if text == ".:" else text[2:-1].rstrip("/") + "/"
        elif entry:
            self._long_entry(entry, line)
        elif re.match(r"total\b", text):
            pass
        elif re.fullmatch(r"\[?[\w.\-]+/?\]?", text) and not self.recursive:
            if not text.startswith("["):                     # [bracketed] entries are optional; a bare name may be name.md or a folder
                self.found.append((text, line, True))
        else:
            return False
        return True

    def _long_entry(self, entry: re.Match[str], line: Line) -> None:
        name = entry.group(2)
        if name in (".", ".."):
            return
        path = self.folder + name + ("/" if entry.group(1) == "d" else "")
        if path.rstrip("/").count("/") <= 1:
            self.found.append((path, line, self.example))


def layout_files(lines: list[Line]) -> list[tuple[str, Line, bool]]:
    """(path, line, is_example) from every listing of the expected layout, only after a sentence about the layout of the repository."""
    out: list[tuple[str, Line, bool]] = []
    for i, line in enumerate(lines):
        if not re.match(r"\$>?\s*ls\b", line.text):
            continue
        context = " ".join(l.text for l in lines[max(0, i - 3): i]).lower()
        if not re.search(r"directory structure|repository layout|layout must|must (?:include|contain)", context):
            continue
        out += LayoutListing(lines, i, "example" in context).read()
    return out
