"""What the project says about its submodules: where they sit, which commit it records, and where they come from."""

from __future__ import annotations

import re
from pathlib import Path

from verdict.repository.repo.git.client import GitClient

SUBMODULE_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*){0,3}")


def submodule_paths(root: Path) -> list[str]:
    """The folders .gitmodules says are submodules (read as plain text: nothing is run)."""
    try:
        text = (root / ".gitmodules").read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return []
    return [m["path"] for m in re.finditer(r"^\s*path\s*=\s*(?P<path>\S+)\s*$", text, re.M) if SUBMODULE_PATH.fullmatch(m["path"])]


def empty_submodules(root: Path) -> list[str]:
    """Submodule folders of `root` that hold nothing: they were never downloaded."""
    out = []
    for path in submodule_paths(root):
        folder = root / path
        if folder.is_symlink() or (folder.is_dir() and not any(folder.iterdir())) or not folder.exists():
            out.append(path)
    return out


class GitModules:
    """Reads the submodules a project records, through git (the project's own files are only data)."""

    def __init__(self, client: GitClient) -> None:
        self.client = client

    def gitlinks(self, root: Path) -> dict[str, str]:
        """path -> the commit the project records for each submodule."""
        out = self.client.run("ls-files", "-s", "-z", folder=root, config=["core.quotepath=off"], timeout=30).stdout
        links = {}
        for record in out.split("\0"):
            meta, _, path = record.partition("\t")
            parts = meta.split()
            if len(parts) == 3 and parts[0] == "160000" and re.fullmatch(r"[0-9a-f]{40}", parts[1]):
                links[path] = parts[1]
        return links

    def urls(self, root: Path) -> dict[str, str]:
        """path -> url, from .gitmodules."""
        out = self.client.run("config", "-f", ".gitmodules", "--null", "--list", folder=root, timeout=30).stdout
        settings: dict[str, dict[str, str]] = {}
        for record in out.split("\0"):
            key, _, value = record.partition("\n")
            if key.startswith("submodule.") and "." in key[len("submodule."):]:
                name, _, var = key[len("submodule."):].rpartition(".")
                settings.setdefault(name, {})[var] = value
        return {v["path"]: v.get("url", "") for v in settings.values() if "path" in v}
