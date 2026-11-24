"""The subject library on disk: one folder per curriculum track (samples/<track>/*.pdf), and the Norm at the root."""

from __future__ import annotations

import os
from pathlib import Path

from verdict.core.errors import Conflict, Failed, NotFound, TooLarge, VerdictError

TRACKS = {"common-core": "Common Core", "post-common-core": "Post Common Core", "rncp": "RNCP"}
NORM_PDF = "en.norm.pdf"
MAX_PDF_BYTES = 30 * 1024 * 1024


class LibraryService:
    """Repository over the samples folder. An upload never replaces a file with other content, nor writes through a link."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def norm_path(self) -> Path:
        return self.root / NORM_PDF

    def files(self) -> dict[str, Path]:
        """Subject PDFs in the library, by their path inside it: `common-core/libft.pdf`, or `common-core/cpp-modules/cpp00.pdf` when the
        PDF is in the folder of its series (one level of folders, like the projects folder)."""
        found: dict[str, Path] = {}
        for track in TRACKS:
            folder = self.root / track
            for pdf in sorted(self._pdfs_of(folder)):
                found[f"{track}/{pdf.relative_to(folder).as_posix()}"] = pdf
        return found

    def find(self, track: str, name: str) -> Path | None:
        """The PDF called `name` in a track, wherever it is filed in it."""
        return next((pdf for rel, pdf in self.files().items() if rel.split("/", 1)[0] == track and pdf.name == name), None)

    @staticmethod
    def _pdfs_of(folder: Path) -> list[Path]:
        """The PDFs of a track folder and of its series folders; no link is followed and nothing hidden counts."""
        if not folder.is_dir() or folder.is_symlink():
            return []
        found = []
        for current, folders, names in os.walk(folder, followlinks=False):
            folders[:] = [d for d in folders if not d.startswith(".") and not (Path(current) / d).is_symlink()]
            found += [Path(current) / n for n in names if n.lower().endswith(".pdf") and not n.startswith(".")
                      and (Path(current) / n).is_file() and not (Path(current) / n).is_symlink()]
        return found

    def listing(self) -> dict:
        return {"tracks": [{"id": track, "label": label} for track, label in TRACKS.items()],
                "items": [self._item(rel, path) for rel, path in self.files().items()], "norm": self.norm_path.is_file()}

    def path_of(self, rel: str) -> Path:
        try:
            return self.files()[rel]
        except KeyError:
            raise NotFound(f"{rel} is not in the library") from None

    def upload(self, track: str, name: str, data: bytes) -> dict:
        """Keep an uploaded PDF in the library folder of its track, unless that exact file is already there."""
        self._check(track, name, data)
        existing = self.find(track, name)                       # filed anywhere in the track, in a series folder or not
        if existing is not None:
            if existing.read_bytes() != data:
                raise Conflict(f"samples/{existing.relative_to(self.root).as_posix()} already exists with different content. "
                               "Rename the file, or remove the old one from the folder first.")
            return self._item(existing.relative_to(self.root).as_posix(), existing)
        self._save(self._slot(track, name), data)
        return self._item(f"{track}/{name}", self.root / track / name)

    @staticmethod
    def _item(rel: str, path: Path) -> dict:
        return {"path": rel, "name": path.name, "track": rel.split("/", 1)[0], "size": path.stat().st_size}

    @staticmethod
    def _check(track: str, name: str, data: bytes) -> None:
        if track not in TRACKS:
            raise VerdictError(f"choose where the subject belongs: {', '.join(TRACKS.values())}")
        if len(data) > MAX_PDF_BYTES:
            raise TooLarge(f"{name} is larger than {MAX_PDF_BYTES // 2**20} MB")
        if not data.startswith(b"%PDF"):
            raise VerdictError(f"{name} is not a PDF")
        if name == NORM_PDF:
            raise VerdictError(f"{NORM_PDF} is the Norm: it is added automatically whenever C code is detected")

    def _slot(self, track: str, name: str) -> Path:
        """Where a new upload goes: at the top of its track (nothing is filed in a series folder by an upload)."""
        target = self.root / track / name
        if target.is_symlink() or target.exists():
            raise Conflict(f"samples/{track}/{name} is a link; it was not replaced")
        return target

    @staticmethod
    def _save(target: Path, data: bytes) -> None:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.upload")
            temporary.write_bytes(data)
            os.replace(temporary, target)
        except OSError as exc:
            raise Failed(f"could not save {target.name} into samples/{target.parent.name}/: {exc.strerror}") from exc
