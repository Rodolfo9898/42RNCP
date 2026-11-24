"""Which repository a review is about: cloned from GitHub, or a folder that is already in the projects folder."""

from __future__ import annotations

from pathlib import Path

from verdict.core.errors import VerdictError
from verdict.projects.folders import ProjectFolders
from verdict.repository import repo as repo_mod
from verdict.sessions.refresh import ContextRefresher
from verdict.sessions.store import RepoMeta, Session, Store


class ProjectService:
    def __init__(self, store: Store, folders: ProjectFolders, refresher: ContextRefresher, known_hosts: Path) -> None:
        self.store, self.folders, self.refresher, self.known_hosts = store, folders, refresher, known_hosts

    def clone(self, session: Session, url: str, name: str = "", destination: str = "") -> None:
        try:
            url = repo_mod.validate_url(url)
            name = name.strip() or repo_mod.default_name(url)
            dest = repo_mod.resolve_destination(self.folders.root, destination, name)
        except repo_mod.RepoError as exc:
            raise VerdictError(str(exc)) from exc
        session.state, session.message = "cloning", ""
        try:
            info = repo_mod.clone(url, dest, self.known_hosts)
        except repo_mod.RepoError as exc:
            session.state, session.message = "error", str(exc)
            self.store.save(session)
            raise VerdictError(str(exc)) from exc
        self._attach(session, info, name, self.folders.relative(dest))

    def use_existing(self, session: Session, path: str) -> None:
        """Review a folder that is already in the projects folder instead of cloning one."""
        try:
            folder, info = repo_mod.use_existing(self.folders.root, path)
        except repo_mod.RepoError as exc:
            raise VerdictError(str(exc)) from exc
        self._attach(session, info, folder.name, self.folders.relative(folder))

    def _attach(self, session: Session, info: repo_mod.RepoInfo, name: str, path: str) -> None:
        session.repo = RepoMeta(**info.__dict__, name=name, path=path)
        session.results, session.state, session.message = [], "idle", ""
        self.refresher.refresh(session)
        self.store.save(session)
