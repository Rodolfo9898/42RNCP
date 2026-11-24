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
        """Subject PDFs in the library, by their path inside it (`common-core/libft.pdf`)."""
        found: dict[str, Path] = {}
        for track in TRACKS:
            folder = self.root / track
            for pdf in sorted(folder.glob("*.pdf")) if folder.is_dir() else []:
                if pdf.is_file() and not pdf.is_symlink():
                    found[f"{track}/{pdf.name}"] = pdf
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
        target = self._slot(track, name, data)
        if target is not None:
            self._save(target, data)
        rel = f"{track}/{name}"
        return self._item(rel, self.root / rel)

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

    def _slot(self, track: str, name: str, data: bytes) -> Path | None:
        """Where an upload goes, or None when that exact file is already there."""
        target = self.root / track / name
        if target.is_symlink():
            raise Conflict(f"samples/{track}/{name} is a link; it was not replaced")
        if target.exists():
            if target.read_bytes() == data:
                return None
            raise Conflict(f"samples/{track}/{name} already exists with different content. "
                           "Rename the file, or remove the old one from the folder first.")
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
