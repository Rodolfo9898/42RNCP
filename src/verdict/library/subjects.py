"""The subjects of a review: added from the library, removed, and read again when the parser improves."""

from __future__ import annotations

from verdict.core.errors import VerdictError
from verdict.library.catalog import NORM_PDF, LibraryService
from verdict.library.files import SubjectFiles
from verdict.library.norm import NormAttachment
from verdict.sessions.refresh import ContextRefresher
from verdict.sessions.store import Session, Store, Subject
from verdict.subjects.pdf import read_pages
from verdict.subjects.spec import parse_subject

MAX_SUBJECTS = 20


class SubjectService:
    def __init__(self, store: Store, library: LibraryService, files: SubjectFiles, norm: NormAttachment,
                 refresher: ContextRefresher) -> None:
        self.store, self.library, self.files, self.norm, self.refresher = store, library, files, norm, refresher

    def add_from_library(self, session: Session, paths: list[str]) -> None:
        found = [(rel, self.library.path_of(rel)) for rel in paths]       # all of them exist, or none is added
        for rel, path in found:
            self._add(session, path.name, path.read_bytes(), rel.split("/", 1)[0])
        self._settle(session)

    def remove(self, session: Session, name: str) -> None:
        subject = session.subjects.get(name)
        if subject is not None and subject.kind == "norm":
            raise VerdictError("The Norm applies to every C project; it goes away by itself when no C is detected.")
        session.subjects.pop(name, None)
        self.files.drop(session, name)
        session.results = []
        self._settle(session)

    def refresh_rules(self, session: Session) -> bool:
        """Read every subject's PDF again with the parser as it is now. The rules are stored in the session when a subject is added, so
        without this an improvement of the parser would never reach a review that already had the subject. A subject whose PDF is gone
        keeps the rules it has. True when something changed."""
        changed = False
        for name, subject in list(session.subjects.items()):
            fresh = self._read_again(session, name, subject)
            if fresh is not None and (fresh.rules, fresh.lang, fresh.pages) != (subject.rules, subject.lang, subject.pages):
                session.subjects[name] = fresh
                changed = True
        return changed

    def _read_again(self, session: Session, name: str, subject: Subject) -> Subject | None:
        try:
            if subject.kind == "norm":
                return self.norm.subject()
            pages = read_pages(self.files.pdf(session, name))
            spec = parse_subject(name, pages)
            return Subject(name=name, track=subject.track, lang=spec.lang, pages=len(pages), rules=spec.rules)
        except Exception:                                  # (an unreadable or missing PDF: keep what the session has)
            return None

    def _add(self, session: Session, name: str, data: bytes, track: str) -> None:
        if not data.startswith(b"%PDF"):
            raise VerdictError(f"{name} is not a PDF")
        if name == NORM_PDF:
            raise VerdictError(f"{NORM_PDF} is the Norm: it is added automatically whenever C code is detected")
        if len(session.subjects) >= MAX_SUBJECTS and name not in session.subjects:
            raise VerdictError(f"at most {MAX_SUBJECTS} subjects per session")
        try:
            pages = read_pages(data)
        except Exception as exc:
            raise VerdictError(f"could not read {name}: {exc}") from exc
        spec = parse_subject(name, pages)
        session.subjects[name] = Subject(name=name, track=track, lang=spec.lang, pages=len(pages), rules=spec.rules)
        session.results = []
        session.state = "idle"
        self.files.keep(session, name, data)

    def _settle(self, session: Session) -> None:
        self.refresher.refresh(session)
        self.store.save(session)
