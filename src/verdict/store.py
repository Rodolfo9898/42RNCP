"""Sessions: a set of subject PDFs, one cloned repo, and the latest check results."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .models import AIState, CheckResult, ClaudeReport, Improvement, ReviewItem, Rule
from .spec import merge_rules

ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,32}$")


class Subject(BaseModel):
    name: str
    lang: str | None = None
    pages: int = 0
    rules: list[Rule] = Field(default_factory=list)


class RepoMeta(BaseModel):
    url: str
    name: str = ""
    path: str = ""  # relative to the projects folder
    commit: str
    subject: str = ""
    author: str = ""


class Session(BaseModel):
    id: str
    created: str
    subjects: dict[str, Subject] = Field(default_factory=dict)
    repo: RepoMeta | None = None
    results: list[CheckResult] = Field(default_factory=list)
    improvements: list[Improvement] = Field(default_factory=list)
    readme: dict = Field(default_factory=dict)
    ai: AIState = Field(default_factory=AIState)
    claude_review: str = ""       # the report claude saved in the terminal (claude-review.md), shown in verdict.md
    claude_review_at: str = ""
    claude: ClaudeReport = Field(default_factory=ClaudeReport)
    review_items: list[ReviewItem] = Field(default_factory=list)   # numbering of the requirements in the last prompt
    claude_review_file: str = ""   # name of claude's report inside the cloned repository
    verdict_file: str = ""  # name of the verdict written into the repository
    state: Literal["idle", "cloning", "running", "done", "error"] = "idle"
    message: str = ""

    def rules(self) -> list[Rule]:
        return merge_rules([r for s in self.subjects.values() for r in s.rules])

    def lang(self) -> str | None:
        langs = {s.lang for s in self.subjects.values() if s.lang}
        return "cpp" if "cpp" in langs else ("c" if "c" in langs else None)


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, Session] = {}
        self.lock = threading.RLock()

    def path(self, session_id: str) -> Path:
        if not ID_RE.match(session_id):
            raise KeyError(session_id)
        return self.root / session_id

    def create(self) -> Session:
        session = Session(id=secrets.token_urlsafe(9), created=datetime.now(timezone.utc).isoformat())
        with self.lock:
            self.path(session.id).mkdir(parents=True)
            self._sessions[session.id] = session
            self.save(session)
        return session

    def get(self, session_id: str) -> Session:
        with self.lock:
            if session_id in self._sessions:
                return self._sessions[session_id]
            file = self.path(session_id) / "session.json"
            if not file.is_file():
                raise KeyError(session_id)
            session = Session.model_validate_json(file.read_text())
            if session.state in ("cloning", "running"):  # the process that was running it is gone
                session.state, session.message = "error", "Interrupted by a restart."
            if session.ai.state == "running":
                session.ai.state, session.ai.message = "error", "Interrupted by a restart."
            self._sessions[session_id] = session
            return session

    def save(self, session: Session) -> None:
        with self.lock:
            tmp = self.path(session.id) / "session.json.tmp"
            tmp.write_text(session.model_dump_json(indent=1))
            os.replace(tmp, self.path(session.id) / "session.json")

    def delete(self, session_id: str) -> None:
        with self.lock:
            self._sessions.pop(session_id, None)
            shutil.rmtree(self.path(session_id), ignore_errors=True)


def safe_filename(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^\w.\- ]", "_", base).strip(" .") or "subject.pdf"
    return base if base.lower().endswith(".pdf") else base + ".pdf"
