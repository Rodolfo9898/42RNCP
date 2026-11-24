"""src/terminal/editor/installer.py: installing what the list asks for, and following what the editor installs."""

import subprocess
import threading
import time

from terminal.editor.extensions import ExtensionList, InstalledExtensions
from terminal.editor.installer import ExtensionInstaller, ExtensionWatcher
from tests.terminal.fakes import manifest


class WatchedManifest(InstalledExtensions):
    """Counts how often the manifest was looked at: the watcher looks once to install, once for its baseline, then every few seconds."""

    looks = 0

    def ids(self):
        self.looks += 1
        return super().ids()


def installer_for(world, run, installed=None):
    installed = installed or InstalledExtensions(world.settings.editor.extensions)
    return ExtensionInstaller(world.settings.editor, installed, lambda: {"PATH": "x"}, run=run)


def test_only_the_missing_extensions_are_installed_and_a_failure_is_reported(world):
    manifest(world.settings.editor.extensions, "mhutchie.git-graph")
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs["env"]))
        return subprocess.CompletedProcess(argv, 1 if argv[-1] == "offline.one" else 0, "", "network down")

    assert installer_for(world, run).install_missing(["mhutchie.git-graph", "new.one", "offline.one"]) == ["offline.one"]
    assert [argv[-1] for argv, _ in calls] == ["new.one", "offline.one"], "git-graph is already installed"
    argv, env = calls[0]
    assert argv[:4] == [str(world.settings.editor.server), "--extensions-dir", str(world.settings.editor.extensions), "--install-extension"]
    assert env == {"PATH": "x"}, "installed with the editor's environment: no secret of the service"


def test_the_watcher_installs_the_list_then_keeps_it_in_step_with_the_editor(world):
    editor = world.settings.editor
    listing = ExtensionList(editor.extensions_list)
    listing.path.parent.mkdir()
    installed = WatchedManifest(editor.extensions)
    installs = []
    installer = installer_for(world, lambda argv, **kw: installs.append(argv[-1]) or subprocess.CompletedProcess(argv, 0, "", ""), installed)
    stop = threading.Event()
    watcher = ExtensionWatcher(listing, installed, installer, seconds=0.01)
    thread = threading.Thread(target=watcher.keep_in_step, args=(stop,))
    thread.start()
    try:
        deadline = time.monotonic() + 3
        while not listing.path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert listing.path.exists(), "a missing list is created when its folder is there"
        while installed.looks < 3 and time.monotonic() < deadline:                 # (the baseline is taken: what comes now is a change)
            time.sleep(0.01)
        manifest(editor.extensions, "new.one")                                   # the user installs an extension in the editor
        while listing.read() != ["new.one"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert listing.read() == ["new.one"]
        manifest(editor.extensions)                                              # and uninstalls it
        while listing.read() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert listing.read() == []
    finally:
        stop.set()
        thread.join(timeout=3)
    assert not thread.is_alive() and installs == []


def test_the_watcher_installs_what_the_list_asks_for_when_it_starts(world):
    editor = world.settings.editor
    listing = ExtensionList(editor.extensions_list)
    listing.path.parent.mkdir()
    listing.write(["mhutchie.git-graph", "new.one"])
    manifest(editor.extensions, "mhutchie.git-graph")
    installs = []
    installed = InstalledExtensions(editor.extensions)
    installer = installer_for(world, lambda argv, **kw: installs.append(argv[-1]) or subprocess.CompletedProcess(argv, 0, "", ""), installed)
    stop = threading.Event()
    stop.set()                                                                   # (only the start: no waiting)
    ExtensionWatcher(listing, installed, installer, seconds=0.01).keep_in_step(stop)
    assert installs == ["new.one"]
