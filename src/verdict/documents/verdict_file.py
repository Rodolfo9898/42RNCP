"""verdict.md in the reviewed project: written from the session, and kept the same as the verdict the app shows."""

from __future__ import annotations

import os
import re
from pathlib import Path

from shared.constants import VERDICT_MARKER
from verdict.projects.folders import ProjectFolders
from verdict.reports.report import render_markdown
from verdict.sessions.store import Session, Store
from verdict.sessions.view import chosen_improvements

NAMES = ("verdict.md", "verdict-report.md")                 # the second when the project has a verdict.md of its own
# Earlier versions also saved claude's report into the project under these names. Only verdict.md is written now.
OLD_REVIEW_FILES = ("claude-review.md", "claude-review-report.md")
GENERATED_LINE = re.compile(r"^- Generated: .*$", re.M)


class VerdictFile:
    """Never overwrites a file that is not ours (it must start with the verdict marker), never writes through a link."""

    def __init__(self, folders: ProjectFolders, store: Store) -> None:
        self.folders, self.store = folders, store

    def text(self, session: Session) -> str:
        return render_markdown(
            repo=session.repo.model_dump() if session.repo else None, subjects=list(session.subjects), results=session.results,
            improvements=chosen_improvements(session), readme=session.readme or None, ai=session.ai,
            claude_review=session.claude_review, claude=session.claude,
            project=(session.repo.name or session.repo.path) if session.repo else "")

    def write(self, session: Session) -> None:
        """Save the verdict, with claude's review merged into it, inside the reviewed project. No separate review file is written, and
        one left by an earlier version is removed (never a file of the project's own)."""
        root = self.folders.of(session)
        if root is not None:
            self._delete_ours(root, OLD_REVIEW_FILES)
        session.verdict_file = self._write_generated(root, self.text(session))
        if not session.verdict_file and root is not None:
            session.message = "Could not save the verdict into the repository (no writable file name)."

    def remove(self, session: Session) -> None:
        """Delete the verdict this app wrote into the project. A file of the project's own with such a name is never touched."""
        root = self.folders.of(session)
        if root is not None:
            self._delete_ours(root, (*NAMES, *OLD_REVIEW_FILES))
        session.verdict_file = ""

    def ensure_current(self, session: Session) -> bool:
        """Keep verdict.md the same as the verdict shown in the app: it is written again when it is missing or no longer says what the
        app says (the verdict can change after it was written), and a claude-review.md left by an earlier version is removed. Never
        while a run is in progress."""
        root = self.folders.of(session)
        if root is None or not session.results or session.state == "running" or session.ai.state == "running":
            return False
        if (session.verdict_file and not any(self.is_generated(root / name) for name in OLD_REVIEW_FILES)
                and self._is_current(root / session.verdict_file, self.text(session))):
            return False
        self.write(session)
        self.store.save(session)
        return True

    @staticmethod
    def is_generated(path: Path) -> bool:
        """A regular file (not a link) that this app wrote: it starts with the verdict marker."""
        try:
            return not path.is_symlink() and path.is_file() and path.read_bytes()[:200].startswith(VERDICT_MARKER.encode())
        except OSError:
            return False

    def _delete_ours(self, root: Path, names: tuple[str, ...]) -> None:
        for name in names:
            if self.is_generated(root / name):
                (root / name).unlink(missing_ok=True)

    @staticmethod
    def _is_current(path: Path, text: str) -> bool:
        """Does the file say what the app says now? (Only the 'Generated' time may differ.) A file that is not ours, or that cannot
        be read, is left alone and counts as current."""
        try:
            if path.is_symlink() or not path.is_file():
                return False
            disk = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return True
        if not disk.startswith(VERDICT_MARKER):
            return True
        return GENERATED_LINE.sub("", disk).strip() == GENERATED_LINE.sub("", text).strip()

    @staticmethod
    def _write_generated(root: Path | None, text: str) -> str:
        """Save `text` into the project as the first of NAMES that is free (or ours). Returns the name used, or ""."""
        if root is None or not root.is_dir():
            return ""
        for name in NAMES:
            target = root / name
            if target.is_symlink() or (target.exists() and not VerdictFile.is_generated(target)):
                continue                                   # a link could point outside the project; the project's own file stays
            try:
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o644)
            except OSError:
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            return name
        return ""
