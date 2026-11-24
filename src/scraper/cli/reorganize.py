"""--reorganize: file the PDFs and artifacts you already have in the folders of their series."""
from __future__ import annotations

from scraper.cli.commands import Command
from scraper.core.reporting import Reporter
from scraper.plan.target import Target
from scraper.storage.library import Library
from scraper.storage.reorganize import Reorganizer


class ReorganizeCommand(Command):
    """Offline. With --dry-run it only says what would move."""

    def __init__(self, targets: list[Target], library: Library, reporter: Reporter, *, dry_run: bool = False) -> None:
        self.targets, self.library, self.reporter, self.dry_run = targets, library, reporter, dry_run

    def execute(self) -> None:
        log = self.reporter.log
        reorganizer = Reorganizer(self.library)
        moves = reorganizer.moves(self.targets)
        if not moves:
            log("Everything is already in the folder of its series.")
            return
        base = self.library.samples.parent
        for move in moves:
            log(f"  {move.source.relative_to(base)}  ->  {move.destination.relative_to(base)}")
        if self.dry_run:
            log(f"\n{len(moves)} move(s) would be done (dry run: nothing was moved).")
        else:
            log(f"\n{len(reorganizer.apply(moves))} of {len(moves)} move(s) done.")
