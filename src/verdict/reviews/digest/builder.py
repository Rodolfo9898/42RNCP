"""A bounded, line-numbered text view of a repository, for the AI review.

Repository content is untrusted. It is wrapped in <file> tags with the closing tag neutralised,
so a file cannot end its own block and pose as instructions.
"""

from __future__ import annotations

from pathlib import Path

from verdict.reviews.digest.model import Digest, fence
from verdict.reviews.digest.selection import StudentFiles, priority, read_text

MAX_TREE = 400
NOT_REPORTED_SUFFIXES = (".o", ".a", ".png", ".jpg", ".pdf", ".xpm", ".bmp")     # binaries nobody expects to be read


class DigestBuilder:
    """Builder: lists the files, then adds them one by one in order of importance until the budget of characters is used."""

    def __init__(self, root: Path, max_chars: int = 150_000):
        self.selection = StudentFiles(root)
        self.root = self.selection.root
        self.max_chars = max_chars
        self.digest = Digest(text="", lines={})
        self.blocks: list[str] = []
        self.used = 0

    def build(self) -> Digest:
        tree, candidates = self._candidates()
        for _, posix, rel in candidates:
            self._add(posix, rel)
        listing = "\n".join(tree) + (f"\n… and {len(candidates) - MAX_TREE} more files" if len(candidates) > MAX_TREE else "")
        self.digest.text = "<repository>\n<tree>\n" + fence(listing) + "\n</tree>\n\n" + "\n\n".join(self.blocks) + "\n</repository>"
        return self.digest

    def _candidates(self) -> tuple[list[str], list[tuple[int, str, Path]]]:
        tree: list[str] = []
        candidates: list[tuple[int, str, Path]] = []
        for rel in self.selection.listing():
            posix = rel.as_posix()
            try:
                size = (self.root / rel).stat().st_size
            except OSError:
                continue
            if len(tree) < MAX_TREE:
                tree.append(f"{posix} ({size} bytes)")
            candidates.append((priority(rel), posix, rel))
        candidates.sort(key=lambda c: (c[0], c[1]))
        return tree, candidates

    def _add(self, posix: str, rel: Path) -> None:
        text = read_text(self.root / rel)
        if text is None:
            if (self.root / rel).suffix.lower() not in NOT_REPORTED_SUFFIXES:
                self.digest.omitted.append(posix)
            return
        all_lines = text.split("\n")
        remaining = self.max_chars - self.used
        if remaining < 400:
            self.digest.omitted.append(posix)
            return
        numbered, size, cut = self._numbered(all_lines, remaining)
        if not numbered:
            self.digest.omitted.append(posix)
            return
        header = f'<file path="{fence(posix).replace(chr(34), "")}" lines="{len(all_lines)}"' + (' truncated="true"' if cut else "") + ">"
        self.blocks.append("\n".join([header, fence("\n".join(numbered)), "</file>"]))
        self.used += size + len(header) + 8
        self.digest.lines[posix] = len(all_lines)
        self.digest.included.append(posix)
        if cut:
            self.digest.truncated.append(posix)

    @staticmethod
    def _numbered(all_lines: list[str], remaining: int) -> tuple[list[str], int, bool]:
        """The numbered lines that fit in `remaining` characters, their size, and whether the file was cut."""
        numbered: list[str] = []
        size = 0
        for number, line in enumerate(all_lines, 1):
            entry = f"{number:>5}| {line[:400]}"
            if size + len(entry) + 1 > remaining:
                return numbered, size, True
            numbered.append(entry)
            size += len(entry) + 1
        return numbered, size, False


def build_digest(root: Path, max_chars: int = 150_000) -> Digest:
    return DigestBuilder(root, max_chars).build()
