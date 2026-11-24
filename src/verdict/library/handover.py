"""Handing the PDFs of a review to the terminal container, which cannot see the workspace."""

from __future__ import annotations

import hashlib
import logging

from verdict.library.files import SubjectFiles
from verdict.sessions.store import Session


class SubjectHandover:
    """Only when the terminal does not already have exactly these files. Best effort: a terminal without the PDFs still works."""

    def __init__(self, files: SubjectFiles, terminal) -> None:
        self.files, self.terminal = files, terminal

    def push(self, session: Session) -> None:
        if not self.terminal.configured:
            return
        try:
            folder = self.files.sync(session)
            pdfs = {p.name: p for p in sorted(folder.glob("*.pdf")) if p.is_file() and not p.is_symlink() and p.name in session.subjects}
            digests = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in pdfs.items()}
            if pdfs and self.terminal.subject_digests(session.id) != digests:
                self.terminal.put_subjects(session.id, {name: path.read_bytes() for name, path in pdfs.items()})
        except Exception:
            logging.getLogger("verdict").warning("could not hand the subject PDFs to the terminal", exc_info=True)
