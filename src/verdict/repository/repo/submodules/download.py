"""Downloading one submodule into the disposable copy of a project."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from verdict.repository.repo.git.client import GitClient
from verdict.repository.repo.model.records import SubmoduleNote
from verdict.repository.repo.submodules.gitmodules import SUBMODULE_PATH
from verdict.repository.repo.submodules.policy import HTTPS


class SourcePolicy(Protocol):
    def source(self, url: str) -> str | None: ...


def empty_folder(folder: Path) -> None:
    """Back to the empty folder it was: what a failed download left behind goes."""
    for child in folder.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


class SubmoduleDownload:
    """Clones one submodule at the commit the project records, from an address the policy allows (Strategy: the policy).

    Never writes outside the project, never contacts an address the policy refuses, and tries a private GitHub library again
    through the ssh-agent.
    """

    TIMEOUT = 180       # for one download

    def __init__(self, client: GitClient, policy: SourcePolicy, protocols: tuple[str, ...], clock: Callable[[], float]) -> None:
        self.client, self.policy, self.protocols, self.clock = client, policy, protocols, clock

    def fetch(self, root: Path, path: str, sha: str, url: str, shown: str, deadline: float) -> SubmoduleNote:
        dest = root / path
        refusal = self._refusal(root, path, url, shown, dest)
        if refusal is not None:
            return refusal
        addresses = self._addresses(url)
        last = ""
        for address in addresses:
            left = deadline - self.clock()
            if left <= 1:
                return SubmoduleNote(shown, False, "ran out of time downloading submodules")
            last = self._clone(address, dest, left)
            if not last:
                break
        if last:
            return SubmoduleNote(shown, False, last)
        return self._checkout(dest, sha, shown, deadline)

    def _refusal(self, root: Path, path: str, url: str, shown: str, dest: Path) -> SubmoduleNote | None:
        """The note that says why this one is not downloaded, or None when it may be."""
        if not SUBMODULE_PATH.fullmatch(path) or ".git" in path.split("/"):
            return SubmoduleNote(shown, False, "its folder name is not one this app will write to")
        if not dest.parent.resolve().is_relative_to(root.resolve()) or dest.is_symlink():
            return SubmoduleNote(shown, False, "its folder is a link or leaves the project")
        if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
            return SubmoduleNote(shown, True, "already there")
        if not url:
            return SubmoduleNote(shown, False, ".gitmodules gives no address for it")
        source = self.policy.source(url)
        if source is None:
            return SubmoduleNote(shown, False, f"{url} is not an address this app downloads from (github.com, gitlab.com, bitbucket.org, codeberg.org, or the project's own host)")
        if source == "ssh" and not self.client.has_agent:
            return SubmoduleNote(shown, False, f"{url} needs your ssh-agent, which is not available")
        return None

    def _addresses(self, url: str) -> list[str]:
        addresses = [url]
        if self.policy.source(url) == "https" and self.client.has_agent and (m := HTTPS.match(url)) and m["host"].lower() == "github.com":
            addresses.append("git@github.com:" + url[len("https://github.com/"):])        # a private repository: the same repository, through your agent
        return addresses

    def _clone(self, address: str, dest: Path, left: float) -> str:
        """'' when the download worked, else why it did not (the folder is left empty)."""
        settings = ["core.hooksPath=/dev/null", "protocol.allow=never", "credential.helper=",
                    *(f"protocol.{proto}.allow=always" for proto in self.protocols)]
        dest.mkdir(parents=True, exist_ok=True)
        try:
            done = self.client.run("clone", "-q", "--no-recurse-submodules", "--", address, str(dest), config=settings,
                                   timeout=min(self.TIMEOUT, left))
        except subprocess.TimeoutExpired:
            empty_folder(dest)
            return "the download timed out"
        if done.returncode == 0:
            return ""
        empty_folder(dest)
        return (done.stderr.strip().splitlines() or ["git clone failed"])[-1]

    def _checkout(self, dest: Path, sha: str, shown: str, deadline: float) -> SubmoduleNote:
        checkout = self._detach(dest, sha)
        if checkout.returncode != 0:                                                       # a commit that is not on a branch the clone fetched
            self.client.run("fetch", "-q", "origin", sha, folder=dest, timeout=min(self.TIMEOUT, max(1.0, deadline - self.clock())))
            checkout = self._detach(dest, sha)
        if checkout.returncode != 0:
            return SubmoduleNote(shown, False, f"downloaded, but the commit {sha[:7]} the project records is not in it")
        return SubmoduleNote(shown, True, f"downloaded at {sha[:7]}")

    def _detach(self, dest: Path, sha: str) -> subprocess.CompletedProcess:
        return self.client.run("checkout", "-q", "--detach", sha, folder=dest, config=["advice.detachedHead=false"], timeout=60)
