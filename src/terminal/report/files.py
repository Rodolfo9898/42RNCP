"""Where claude saves its report, and the files of it that are ours to touch."""

from pathlib import Path

from terminal.settings.folders import SessionFolders

REVIEW_FILE = "claude-review.md"


class ReportFiles:
    """The report of a review: `$REPORTS_ROOT/<sid>/claude-review.md`, outside the project (claude finds the folder in $REPORT_DIR)."""

    def __init__(self, folders: SessionFolders) -> None:
        self.folders = folders

    def saved(self, session_id: str) -> Path | None:
        """Where claude's report of this review is (or will be); None for an id that is not a session id."""
        folder = self.folders.reports(session_id)
        return folder / REVIEW_FILE if folder else None

    def prepare(self, session_id: str) -> Path:
        """The review's report folder, made ready for claude to write into."""
        folder = self.folders.reports(session_id)
        if folder is None:
            raise ValueError(f"not a session id: {session_id!r}")
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def started(self, session_id: str) -> bool:
        """Was claude started for this review? (Its report folder exists.)"""
        folder = self.folders.reports(session_id)
        return folder is not None and folder.is_dir()

    def discard(self, session_id: str) -> bool:
        """Deletes the saved report, so that a new pass starts without the last one's (or it would be merged as if claude had just
        written it). Only the report: what else is in the folder stays. A link is removed, never followed."""
        saved = self.saved(session_id)
        if saved is None:
            return False
        try:
            saved.unlink()
        except OSError:
            return False
        return True
