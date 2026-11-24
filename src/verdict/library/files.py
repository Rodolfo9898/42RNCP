"""The PDFs of a review on disk: workspace/<session>/subjects/, one copy per subject (and the Norm), kept in step with the session."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from verdict.core.errors import NotFound
from verdict.library.catalog import NORM_PDF, TRACKS, LibraryService
from verdict.sessions.store import Session, Store, safe_filename


class SubjectFiles:
    """The sandbox reads this folder as $SUBJECTS_DIR for the checks, and the terminal container gets a copy of it (SubjectHandover)."""

    def __init__(self, store: Store, library: LibraryService) -> None:
        self.store, self.library = store, library

    def directory(self, session: Session) -> Path:
        return self.store.path(session.id) / "subjects"

    def pdf(self, session: Session, name: str) -> Path:
        """The PDF of a subject of this session: its own copy, or the library file (sessions made before copies were kept)."""
        subject = session.subjects.get(name)
        if subject is None:
            raise NotFound(f"{name} is not a subject of this session")
        candidates = [self.directory(session) / name]
        if subject.kind == "norm":
            candidates.append(self.library.norm_path)
        elif subject.track in TRACKS:
            candidates.append(self.library.root / subject.track / name)
        for path in candidates:
            if path.is_file() and not path.is_symlink():
                return path
        raise NotFound(f"the PDF of {name} is no longer available; add it again")

    def keep(self, session: Session, name: str, data: bytes) -> None:
        """A copy of its own, so the PDF can be shown whatever happens to the library."""
        target = self.directory(session) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def drop(self, session: Session, name: str) -> None:
        (self.directory(session) / safe_filename(name)).unlink(missing_ok=True)

    def sync(self, session: Session) -> Path:
        """The folder with the PDFs of this review: the subjects you chose or uploaded, and the Norm while it applies, and nothing else."""
        folder = self.directory(session)
        folder.mkdir(parents=True, exist_ok=True)
        for name in session.subjects:
            self._copy_missing(session, folder, name)
        for stale in folder.iterdir():
            if stale.is_file() and not stale.is_symlink() and stale.suffix.lower() == ".pdf" and stale.name not in session.subjects:
                stale.unlink(missing_ok=True)              # a subject that was removed, or the Norm when C is no longer detected
        return folder

    def _copy_missing(self, session: Session, folder: Path, name: str) -> None:
        target = folder / name
        try:
            source = self.pdf(session, name)
        except NotFound:
            return                                         # the file is gone (an old session): nothing to hand over
        if source.resolve() == target.resolve() or (target.exists() and target.stat().st_size == source.stat().st_size):
            return
        fd, temporary = tempfile.mkstemp(dir=folder, prefix=".copy-")
        with os.fdopen(fd, "wb") as fh:
            fh.write(source.read_bytes())
        os.chmod(temporary, 0o444)                         # read-only for anything that runs in the sandbox by accident
        os.replace(temporary, target)


__all__ = ["NORM_PDF", "SubjectFiles"]
