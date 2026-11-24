"""What is on disk: the subject PDFs in samples/<track>/, and the artifacts in artifacts/<stem>/."""
from __future__ import annotations

import json
from pathlib import Path

from scraper.plan.names import key
from scraper.plan.tracks import TRACKS


class Library:
    CHECKED = ".checked.json"     # the stems whose page was read in full: such a project is not visited again

    def __init__(self, samples: Path, artifacts: Path) -> None:
        self.samples, self.artifacts = samples, artifacts

    def pdfs(self) -> dict[str, Path]:
        """Spelling-insensitive name -> the PDF, over every track (a subject is the same one wherever it was put)."""
        found: dict[str, Path] = {}
        for track in TRACKS:
            for pdf in sorted((self.samples / track).glob("*.pdf")):
                found.setdefault(key(pdf.stem), pdf)
        return found

    def find_pdf(self, stem: str) -> Path | None:
        return self.pdfs().get(key(stem))

    def pdf_path(self, track: str, stem: str) -> Path:
        return self.samples / track / f"{stem}.pdf"

    def artifact_dir(self, stem: str) -> Path:
        return self.artifacts / stem

    def artifact_files(self, stem: str) -> list[Path]:
        folder = self.artifact_dir(stem)
        if not folder.is_dir():
            return []
        return sorted(f for f in folder.rglob("*") if f.is_file() and f.suffix != ".part" and f.name != ".DS_Store")

    def checked(self) -> set[str]:
        try:
            return set(json.loads((self.artifacts / self.CHECKED).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return set()

    def mark_checked(self, stem: str) -> None:
        done = self.checked() | {stem}
        self.artifacts.mkdir(parents=True, exist_ok=True)
        (self.artifacts / self.CHECKED).write_text(json.dumps(sorted(done), indent=1) + "\n", encoding="utf-8")
