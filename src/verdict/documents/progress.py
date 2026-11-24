"""Progress.md: record the result the verdict shows now in the row of its project."""

from __future__ import annotations

import threading
from pathlib import Path

from verdict.core.errors import NotFound, Unavailable, VerdictError
from verdict.reports import progress as table
from verdict.reports.report import summarize
from verdict.sessions.store import Session


class ProgressService:
    """Pressed on purpose, once you accept the result: it never happens by itself."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.Lock()

    def record(self, session: Session) -> dict:
        if self.path is None:
            raise NotFound("Progress.md is not available: start the app with `make run` (it mounts the file)")
        if session.repo is None or not session.results:
            raise VerdictError("run the checks first: there is no result to record yet")
        project = session.repo.name or Path(session.repo.path).name
        result = summarize(session.results, session.ai, session.claude)["overall"]
        try:
            symbol = table.symbol_for(result)
            before = self._update(project, symbol)
        except table.ProgressError as exc:
            raise VerdictError(str(exc)) from exc
        except OSError as exc:
            raise Unavailable(f"Progress.md cannot be written ({exc.strerror or exc})") from exc
        return {"project": project, "result": result, "symbol": symbol, "before": before, "changed": before != symbol}

    def _update(self, project: str, symbol: str) -> str | None:
        with self._lock:
            text = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""
            new, before = table.update(text, project, symbol)
            if new != text:
                self.path.write_text(new, encoding="utf-8")       # in place: the file keeps its identity on the host
            return before
