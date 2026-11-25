"""What is on disk: the subject PDFs in samples/<track>/[<group>/], and the artifacts in artifacts/[<group>/]<name>/."""
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from scraper.plan.names import key
from scraper.plan.target import Target
from scraper.plan.tracks import TRACKS


class Library:
    CHECKED = ".checked.json"     # the stems whose page was read in full: such a project is not visited again

    def __init__(self, samples: Path, artifacts: Path) -> None:
        self.samples, self.artifacts = samples, artifacts

    def pdfs(self) -> dict[str, Path]:
        """Spelling-insensitive name -> the PDF, over every track and every folder (a subject is the same one wherever it was put)."""
        found: dict[str, Path] = {}
        for track in TRACKS:
            for pdf in sorted((self.samples / track).rglob("*.pdf")):
                found.setdefault(key(pdf.stem), pdf)
        return found

    def find_pdf(self, stem: str) -> Path | None:
        return self.pdfs().get(key(stem))

    def missing(self, targets: Sequence[Target]) -> list[Target]:
        """The projects that have no PDF yet (the folder is read once for all of them)."""
        pdfs = self.pdfs()
        return [t for t in targets if key(t.stem) not in pdfs]

    def visits(self, targets: Sequence[Target], *, with_artifacts: bool, force: bool = False) -> list[Target]:
        """The projects whose page has to be read: the PDF is missing or, if the artifacts are wanted, the page has not been read in
        full yet (`force`: all of them)."""
        if force:
            return list(targets)
        pdfs, checked = self.pdfs(), self.checked()
        return [t for t in targets if key(t.stem) not in pdfs or (with_artifacts and t.stem not in checked)]

    def shown(self, path: Path) -> str:
        """A path the way a person reads it: from the folder that holds samples/ (or artifacts/)."""
        for base in (self.samples.parent, self.artifacts.parent):
            if path.is_relative_to(base):
                return path.relative_to(base).as_posix()
        return path.name

    def pdf_path(self, target: Target) -> Path:
        """Where the subject of a project goes: its track, the folder of its series if it has one, its name."""
        return self.samples.joinpath(target.track, *target.folders, f"{target.stem}.pdf")

    def artifact_dir(self, target: Target) -> Path:
        return self.artifacts.joinpath(*target.folders, target.stem)

    def artifact_files(self, target: Target) -> list[Path]:
        folder = self.artifact_dir(target)
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
