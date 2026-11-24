"""The editor's extensions: the list in config/extensions.txt, and what is installed."""

from __future__ import annotations

import json
import re
from pathlib import Path

EXTENSION_ID = re.compile(r"[A-Za-z0-9][\w-]*\.[A-Za-z0-9][\w.-]*")
HEADER = ("# VS Code extensions (Open VSX ids, publisher.name), installed when the editor starts if they are not already.\n"
          "# An extension you install or uninstall in the editor is added here or taken off by itself. `#` starts a comment.\n")


class ExtensionList:
    """config/extensions.txt: one id per line (publisher.name), `#` starts a comment."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> list[str]:
        """The ids of the list, in order, lower-cased, without comments, blank lines or anything that is not an id."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        ids: list[str] = []
        for line in lines:
            word = line.split("#", 1)[0].strip().lower()
            if EXTENSION_ID.fullmatch(word) and word not in ids:
                ids.append(word)
        return ids

    def write(self, ids: list[str]) -> None:
        """The list with these ids, sorted, under the comments the file starts with (or the usual header). Written in place: the file
        is a bind mount of config/extensions.txt, which a rename into it would replace by a file the host never sees."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        head = "".join(line + "\n" for line in text.splitlines() if line.startswith("#")) or HEADER
        with open(self.path, "w", encoding="utf-8") as out:
            out.write(head + "".join(f"{i}\n" for i in sorted(set(ids))))

    def sync(self, before: set[str], now: set[str]) -> bool:
        """What changed between two looks at the installed extensions goes into the list: one installed meanwhile is added, one
        uninstalled is taken off. Ids that were never installed (an install that failed) are left alone. True when it wrote."""
        added, removed = now - before, before - now
        if not added and not removed:
            return False
        listed = self.read()
        wanted = [i for i in listed if i not in removed] + sorted(i for i in added if i not in listed)
        if wanted == listed:
            return False
        self.write(wanted)
        return True


class InstalledExtensions:
    """The extensions installed in the editor's folder, from the manifest VS Code keeps there (extensions.json)."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def ids(self) -> set[str]:
        try:
            entries = json.loads((self.folder / "extensions.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        ids = set()
        for entry in entries if isinstance(entries, list) else []:
            ident = (entry.get("identifier") or {}).get("id") if isinstance(entry, dict) else None
            if isinstance(ident, str) and EXTENSION_ID.fullmatch(ident):
                ids.add(ident.lower())
        return ids
