"""Filing what is already on disk where the layout puts it: the PDFs of a series in the folder of the series, and the artifacts too."""
from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scraper.core.utils import prune_empty
from scraper.plan.names import key
from scraper.plan.target import Target
from scraper.storage.library import Library


@dataclass(frozen=True)
class Move:
    source: Path
    destination: Path


class Reorganizer:
    """A PDF is moved inside its own track only, keeps its file name, and never replaces a file; nothing is downloaded or deleted."""

    def __init__(self, library: Library) -> None:
        self.library = library

    def moves(self, targets: Sequence[Target]) -> list[Move]:
        pdfs = self.library.pdfs()                         # the folder is read once, not once per project
        found = []
        for target in targets:
            found += self._subject(target, pdfs.get(key(target.stem))) + self._artifacts(target)
        return found

    def apply(self, moves: Sequence[Move]) -> list[Move]:
        """Do the moves that are still possible; returns the ones done."""
        done = []
        for move in moves:
            if move.destination.exists() or not move.source.exists() or move.source in move.destination.parents:
                continue                                   # (never into itself: a folder cannot move below its own subfolder)
            move.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(move.source), str(move.destination))
            root = self.library.samples if self.library.samples in move.source.parents else self.library.artifacts
            prune_empty(move.source.parent, root)
            done.append(move)
        return done

    def _subject(self, target: Target, existing: Path | None) -> list[Move]:
        if existing is None or self.library.samples / target.track not in existing.parents:
            return []                                      # not there, or in another track: not moved across tracks
        wanted = self.library.pdf_path(target).parent / existing.name
        return [Move(existing, wanted)] if wanted != existing and not wanted.exists() else []

    def _artifacts(self, target: Target) -> list[Move]:
        old = self.library.artifacts / target.stem          # where a run before the series folders put them
        wanted = self.library.artifact_dir(target)
        if target.group == target.stem:                     # the piscine itself: that folder is now the folder of the series, not its own
            return []
        return [Move(old, wanted)] if old.is_dir() and wanted != old and not wanted.exists() else []
