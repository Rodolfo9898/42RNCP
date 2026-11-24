"""Every readable text file of a repository and its line count."""

from __future__ import annotations

from pathlib import Path

from verdict.reviews.digest.selection import StudentFiles, read_text


class LineIndex:
    """Lets citations be checked when the model explores the repository by itself (no digest is sent)."""

    def __init__(self, root: Path):
        self.selection = StudentFiles(root)

    def build(self) -> dict[str, int]:
        lines: dict[str, int] = {}
        for rel in self.selection.listing():
            text = read_text(self.selection.root / rel)
            if text is not None:
                lines[rel.as_posix()] = len(text.split("\n"))
        return lines


def line_index(root: Path) -> dict[str, int]:
    return LineIndex(root).build()
