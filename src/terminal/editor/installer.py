"""Installing the editor's extensions, and keeping the list in step with what the editor has."""

from __future__ import annotations

import subprocess
import sys
import threading
from collections.abc import Callable

from terminal.editor.extensions import ExtensionList, InstalledExtensions
from terminal.settings.editor import EditorSettings


class ExtensionInstaller:
    """Installs, through the editor's own command line (from Open VSX), each extension of the list that is not installed yet."""

    def __init__(self, settings: EditorSettings, installed: InstalledExtensions, environment: Callable[[], dict[str, str]],
                 run=subprocess.run) -> None:
        self.settings, self.installed, self.environment, self.run = settings, installed, environment, run

    def install_missing(self, ids: list[str]) -> list[str]:
        """Installs each id that is not installed yet. Returns the ids that could not be installed."""
        have = self.installed.ids()
        failed = []
        for ident in ids:
            if ident in have:
                continue
            done = self.run([str(self.settings.server), "--extensions-dir", str(self.settings.extensions), "--install-extension", ident],
                            capture_output=True, text=True, timeout=300, env=self.environment())
            if done.returncode != 0:
                failed.append(ident)
                print(f"editor: could not install {ident}: {(done.stderr or done.stdout).strip()[-300:]}", file=sys.stderr)
            else:
                print(f"editor: installed {ident}")
        return failed


class ExtensionWatcher:
    """Installs what the list asks for, then follows what is installed and uninstalled for as long as the editor runs (it polls the
    editor's manifest, and writes what changed into the list, so the next start installs the same set again by itself).
    (Observer, by polling: VS Code offers no event for it.)"""

    def __init__(self, extension_list: ExtensionList, installed: InstalledExtensions, installer: ExtensionInstaller, seconds: int) -> None:
        self.extension_list, self.installed, self.installer, self.seconds = extension_list, installed, installer, seconds

    def keep_in_step(self, stop: threading.Event) -> None:
        listing = self.extension_list
        if listing.path.parent.is_dir() and not listing.path.exists():
            listing.write([])
        self.installer.install_missing(listing.read())
        seen = self.installed.ids()
        while not stop.wait(self.seconds):
            now = self.installed.ids()
            try:
                listing.sync(seen, now)
            except OSError as exc:
                print(f"editor: could not update {listing.path}: {exc}", file=sys.stderr)
                continue
            seen = now
