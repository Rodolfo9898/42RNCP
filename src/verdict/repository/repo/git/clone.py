"""Cloning an untrusted repository. Nothing here executes repo code."""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from verdict.repository.repo.address.urls import validate_url
from verdict.repository.repo.git.client import GitClient
from verdict.repository.repo.git.failures import explain_clone_failure, is_transient
from verdict.repository.repo.git.inspector import FolderInspector
from verdict.repository.repo.model.errors import RepoError
from verdict.repository.repo.model.records import RepoInfo


class Cloner:
    """Template Method: validate, prepare, clone (with one more try when the failure looks like the connection), read the result.

    The clone is a full one (whole history, a real repository with its .git), without submodules, and git is only allowed to speak
    ssh and to run no hook of the repository.
    """

    TIMEOUT = 300       # a full clone (whole history), not a shallow one
    RETRIES = 1         # one more try when the failure looks like the connection, not like a key that is refused for good
    PAUSE = 2
    SETTINGS = ("core.hooksPath=/dev/null", "protocol.allow=never", "protocol.ssh.allow=always", "core.symlinks=true")

    def __init__(self, client: GitClient, inspector: FolderInspector, sleep: Callable[[float], None] = time.sleep) -> None:
        self.client, self.inspector, self.sleep = client, inspector, sleep

    def clone(self, url: str, dest: Path) -> RepoInfo:
        """Clone `url` into `dest` (which must not exist)."""
        url = validate_url(url)
        if dest.exists():
            raise RepoError(f"{dest.name} already exists.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._attempts(url, dest)
        subprocess.run(["chmod", "-R", "u+rwX", str(dest)], check=False)
        return self.inspector.last_commit(dest, url)

    def _attempts(self, url: str, dest: Path) -> None:
        for attempt in range(1 + self.RETRIES):
            try:
                proc = self.client.run("clone", "--no-recurse-submodules", "--", url, str(dest), config=self.SETTINGS, timeout=self.TIMEOUT)
            except subprocess.TimeoutExpired as exc:
                shutil.rmtree(dest, ignore_errors=True)
                raise RepoError(f"git clone timed out after {self.TIMEOUT}s") from exc
            if proc.returncode == 0:
                return
            shutil.rmtree(dest, ignore_errors=True)  # safe: the destination was checked not to exist before the clone
            if attempt < self.RETRIES and is_transient(proc.stderr):
                self.sleep(self.PAUSE)               # a server that answers differently from one connection to the next
                continue
            raise RepoError(explain_clone_failure(proc.stderr, proc.returncode))


def clone(url: str, dest: Path, known_hosts: Path) -> RepoInfo:
    """Clone `url` into `dest` (which must not exist). `known_hosts` is where SSH host keys are remembered."""
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    return Cloner(GitClient.networked(known_hosts), FolderInspector(GitClient.offline())).clone(url, dest)
