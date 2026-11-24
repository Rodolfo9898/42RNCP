"""The Norm: attached to every review where C code is detected, taken away when it is not."""

from __future__ import annotations

from verdict.checks import EXCLUDED_DIRS
from verdict.library.catalog import NORM_PDF, LibraryService
from verdict.projects.folders import ProjectFolders
from verdict.repository import repo as repo_mod
from verdict.sessions.store import Session, Subject
from verdict.subjects.pdf import read_pages
from verdict.subjects.spec import parse_norm

CPP_SUFFIXES = {".cpp", ".cc", ".hpp", ".tpp", ".ipp"}


class NormAttachment:
    def __init__(self, library: LibraryService, folders: ProjectFolders) -> None:
        self.library, self.folders = library, folders
        self._cached: tuple[tuple[int, int], Subject] | None = None      # the parsed Norm, for one version of the file

    def subject(self) -> Subject | None:
        """The Norm from samples/en.norm.pdf (parsed once per version of the file), or None when it is missing."""
        try:
            stat = self.library.norm_path.stat()
        except OSError:
            return None
        key = (stat.st_mtime_ns, stat.st_size)
        if self._cached is None or self._cached[0] != key:
            pages = read_pages(self.library.norm_path.read_bytes())
            spec = parse_norm(NORM_PDF, pages)
            self._cached = (key, Subject(name=NORM_PDF, kind="norm", lang=spec.lang, pages=len(pages), rules=spec.rules))
        return self._cached[1].model_copy(deep=True)

    def applies(self, session: Session) -> bool:
        """C is detected when a subject requires it or, with no language in the subjects, when the repo has C and no C++."""
        lang = session.lang()
        if lang:
            return lang == "c"
        root = self.folders.of(session)
        if root is None or not root.is_dir():
            return False
        suffixes = {p.suffix.lower() for p in repo_mod.tracked_files(root) if not EXCLUDED_DIRS.search("/" + p.as_posix())}
        return ".c" in suffixes and not suffixes & CPP_SUFFIXES

    def sync(self, session: Session) -> None:
        attached = session.subjects.get(NORM_PDF)
        if self.applies(session):
            norm = self.subject() if attached is None or attached.kind != "norm" else None
            if norm is not None:
                session.subjects[NORM_PDF] = norm
                session.results = []
        elif attached is not None and attached.kind == "norm":
            del session.subjects[NORM_PDF]
            session.results = []
