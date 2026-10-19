"""A bounded, line-numbered text view of a repository, for the AI review.

Repository content is untrusted. It is wrapped in <file> tags with the closing tag neutralised,
so a file cannot end its own block and pose as instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .checks import EXCLUDED_DIRS, GENERATED_VERDICT_NAMES, VERDICT_MARKER
from .repo import tracked_files

MAX_FILE_BYTES = 300_000
MAX_TREE = 400
TEXT_NAMES = {"makefile", "dockerfile", "readme", "license", ".gitignore"}


@dataclass
class Digest:
    text: str
    lines: dict[str, int]  # every included file -> its total number of lines (to validate citations)
    included: list[str] = field(default_factory=list)
    truncated: list[str] = field(default_factory=list)  # sent only in part
    omitted: list[str] = field(default_factory=list)    # not sent at all


def _priority(rel: Path) -> int:
    name = rel.name.lower()
    if name.startswith("readme"):
        return 0
    if name in ("makefile", "gnumakefile") or name.endswith(".mk"):
        return 1
    if rel.suffix in (".h", ".hpp"):
        return 2
    if name.startswith("main."):
        return 3
    if rel.suffix in (".c", ".cpp", ".cc", ".tpp", ".ipp", ".py", ".js", ".ts", ".go", ".rs", ".java", ".sh"):
        return 4
    return 5


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _fence(text: str) -> str:
    """Defuse any tag we use as a delimiter (opening or closing) inside untrusted text."""
    return re.sub(r"<(/?)(file|repository|subject_item|tree)\b", r"<\\\1\2", text, flags=re.I)


def build_digest(root: Path, max_chars: int = 150_000) -> Digest:
    root = root.resolve()
    candidates: list[tuple[int, str, Path]] = []
    tree: list[str] = []
    for rel in tracked_files(root):
        posix = rel.as_posix()
        if EXCLUDED_DIRS.search("/" + posix):
            continue
        if len(rel.parts) == 1 and rel.name in GENERATED_VERDICT_NAMES:
            try:
                if (root / rel).read_bytes()[:200].startswith(VERDICT_MARKER.encode()):
                    continue
            except OSError:
                pass
        try:
            size = (root / rel).stat().st_size
        except OSError:
            continue
        if len(tree) < MAX_TREE:
            tree.append(f"{posix} ({size} bytes)")
        candidates.append((_priority(rel), posix, rel))
    candidates.sort(key=lambda c: (c[0], c[1]))

    parts: list[str] = []
    lines: dict[str, int] = {}
    digest = Digest(text="", lines=lines)
    used = 0
    for _, posix, rel in candidates:
        text = _read_text(root / rel)
        if text is None:
            if (root / rel).suffix.lower() not in (".o", ".a", ".png", ".jpg", ".pdf", ".xpm", ".bmp"):
                digest.omitted.append(posix)
            continue
        all_lines = text.split("\n")
        remaining = max_chars - used
        if remaining < 400:
            digest.omitted.append(posix)
            continue
        numbered: list[str] = []
        size = 0
        cut = False
        for number, line in enumerate(all_lines, 1):
            entry = f"{number:>5}| {line[:400]}"
            if size + len(entry) + 1 > remaining:
                cut = True
                break
            numbered.append(entry)
            size += len(entry) + 1
        if not numbered:
            digest.omitted.append(posix)
            continue
        header = f'<file path="{_fence(posix).replace(chr(34), "")}" lines="{len(all_lines)}"' + (' truncated="true"' if cut else "") + ">"
        block = "\n".join([header, _fence("\n".join(numbered)), "</file>"])
        parts.append(block)
        used += size + len(header) + 8
        lines[posix] = len(all_lines)
        digest.included.append(posix)
        if cut:
            digest.truncated.append(posix)

    listing = "\n".join(tree) + (f"\n… and {len(candidates) - MAX_TREE} more files" if len(candidates) > MAX_TREE else "")
    digest.text = (
        "<repository>\n<tree>\n" + _fence(listing) + "\n</tree>\n\n" + "\n\n".join(parts) + "\n</repository>"
    )
    return digest


def line_index(root: Path) -> dict[str, int]:
    """Every readable text file and its line count: lets citations be checked when the model explores by itself."""
    root = root.resolve()
    lines: dict[str, int] = {}
    for rel in tracked_files(root):
        posix = rel.as_posix()
        if EXCLUDED_DIRS.search("/" + posix):
            continue
        if len(rel.parts) == 1 and rel.name in GENERATED_VERDICT_NAMES:
            try:
                if (root / rel).read_bytes()[:200].startswith(VERDICT_MARKER.encode()):
                    continue
            except OSError:
                pass
        text = _read_text(root / rel)
        if text is not None:
            lines[posix] = len(text.split("\n"))
    return lines
