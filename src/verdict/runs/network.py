"""The two steps of a run that need the network: `git pull` in the project, and the project's submodules in the work copy."""

from __future__ import annotations

from pathlib import Path

from verdict.library.norm import NormAttachment
from verdict.projects.folders import ProjectFolders
from verdict.repository import repo as repo_mod
from verdict.sessions.store import RepoMeta, Session


class NetworkSteps:
    def __init__(self, folders: ProjectFolders, norm: NormAttachment, known_hosts: Path) -> None:
        self.folders, self.norm, self.known_hosts = folders, norm, known_hosts

    def pull(self, session: Session) -> str:
        """git pull (fast-forward only) in the project before the checks, so they look at what is on GitHub now. Returns what to say in
        the status bar. Never raises: a pull that cannot be done (no network, local changes in the way) must not stop the checks."""
        if not session.repo or not session.repo.url:
            return ""                                      # a folder without a remote: nothing to pull
        root = self.folders.of(session)
        if root is None or not root.is_dir():
            return ""
        try:
            info, _summary = repo_mod.pull(root, self.known_hosts)
        except repo_mod.RepoError as exc:
            return f"git pull skipped: {exc}"
        changed = info.commit != session.repo.commit
        session.repo = RepoMeta(**info.__dict__, name=session.repo.name, path=session.repo.path)
        self.norm.sync(session)                            # (the new commit may have C code, or no longer have it)
        return f"git pull: now at {info.commit}" if changed else f"git pull: already up to date ({info.commit})"

    def download_submodules(self, session: Session, work: Path) -> list:
        """The sandbox has no network, so the project's submodules (libft, MiniLibX...) are downloaded into the disposable copy here, at
        the commits the project records. Best effort: what cannot be downloaded is reported by the build check, not raised."""
        if not repo_mod.submodule_paths(work):
            return []
        pulled = session.message                           # (what the pull said)
        session.message = "downloading the submodules…"
        try:
            notes = repo_mod.fetch_submodules(work, self.known_hosts, extra_hosts=self._hosts(session))
        except Exception as exc:                           # (it is written not to raise; a bug in it must still not stop the checks)
            notes = [repo_mod.SubmoduleNote("", False, f"{type(exc).__name__}: {exc}")]
        fetched = sum(1 for n in notes if n.ok and n.message.startswith("downloaded"))
        session.message = "; ".join(x for x in (pulled, f"{fetched} submodule(s) downloaded" if fetched else "") if x)
        return notes

    @staticmethod
    def _hosts(session: Session) -> set[str]:
        if session.repo and session.repo.url:
            try:
                return {repo_mod.ssh_target(session.repo.url)[1]}
            except Exception:
                return set()
        return set()
