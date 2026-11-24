"""Where the subject PDFs of the reviews are kept."""

import hashlib
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from shared.constants import is_subject_name
from terminal.settings.folders import SessionFolders
from terminal.settings.limits import Limits


class SubjectStore:
    """The PDFs of each review (its subjects, and the Norm when it applies), one folder per web session. The web app hands them over,
    the terminal has no mount for them, so it still cannot see anything else; claude finds them in $SUBJECTS_DIR, read-only.

    `in_use(sid)` says which reviews still need their folder when old folders are pruned (claude was started for them).
    (Repository: the one place that knows how the PDFs are laid out on disk.)"""

    def __init__(self, folders: SessionFolders, limits: Limits, in_use: Callable[[str], bool]) -> None:
        self.folders, self.limits, self.in_use = folders, limits, in_use

    def digests(self, session_id: str) -> dict[str, str]:
        """The PDFs held for a review, with their hashes, so the web app only sends what is missing or different."""
        folder = self.folders.subjects(session_id)
        if folder is None or not folder.is_dir():
            return {}
        return {p.name: self._sha256(p) for p in sorted(folder.iterdir()) if p.is_file() and not p.is_symlink() and is_subject_name(p.name)}

    def replace(self, session_id: str, received: dict[str, bytes]) -> None:
        """Replaces the PDFs of a review with exactly these: read-only files, written into a staging folder that is renamed into place."""
        final = self.folders.subjects(session_id)
        if final is None:
            raise ValueError(f"not a session id: {session_id!r}")
        root = self.folders.subjects_root
        root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".incoming-", dir=root))
        try:
            for name, data in received.items():
                target = staging / name
                target.write_bytes(data)
                target.chmod(0o444)
            old = root / f".old-{session_id}"
            shutil.rmtree(old, ignore_errors=True)
            if final.exists():
                final.rename(old)
            staging.rename(final)
            shutil.rmtree(old, ignore_errors=True)
        except OSError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        self.prune()

    def prune(self) -> None:
        """Drops the folders of reviews nobody is using and nobody has touched for a while."""
        try:
            folders = [p for p in self.folders.subjects_root.iterdir() if p.is_dir()]
        except OSError:
            return
        for folder in folders:
            if not self.in_use(folder.name) and time.time() - folder.stat().st_mtime > self.limits.stale_subjects_seconds:
                shutil.rmtree(folder, ignore_errors=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                digest.update(chunk)
        return digest.hexdigest()
