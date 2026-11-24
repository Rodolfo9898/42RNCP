"""Reading the report claude saved."""

from terminal.report.files import REVIEW_FILE, ReportFiles
from terminal.settings.limits import Limits


class ReportReader:
    """Reads claude's saved report as data: {"found", "text", "name"}. A link is never followed, a file over the limit or an empty one
    does not count as a report."""

    def __init__(self, files: ReportFiles, limits: Limits) -> None:
        self.files, self.limits = files, limits

    def read(self, session_id: str) -> dict:
        saved = self.files.saved(session_id)
        if saved is not None and saved.is_file() and not saved.is_symlink():
            try:
                if saved.stat().st_size <= self.limits.max_review_bytes and (text := saved.read_text(encoding="utf-8", errors="replace")).strip():
                    return {"found": True, "text": text, "name": REVIEW_FILE}
            except OSError:
                pass
        return {"found": False, "text": "", "name": REVIEW_FILE}
