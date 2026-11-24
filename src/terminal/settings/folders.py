"""Where the files of a review are kept: one folder per web session, named by the session's id."""

import re
from dataclasses import dataclass
from pathlib import Path

SESSION_ID = re.compile(r"[A-Za-z0-9_-]{6,32}")


@dataclass(frozen=True)
class SessionFolders:
    """The layout of the two roots, so that nobody else builds these paths (and nobody builds one from an id that is not an id).

    subjects_root/<sid>/   the PDFs of the review (handed over by the web app, read-only), found by claude in $SUBJECTS_DIR
    reports_root/<sid>/    claude's saved report, outside the project: claude-review.md"""

    subjects_root: Path
    reports_root: Path

    @staticmethod
    def is_valid(session_id: str) -> bool:
        return SESSION_ID.fullmatch(session_id) is not None

    def subjects(self, session_id: str) -> Path | None:
        return self.subjects_root / session_id if self.is_valid(session_id) else None

    def reports(self, session_id: str) -> Path | None:
        return self.reports_root / session_id if self.is_valid(session_id) else None
