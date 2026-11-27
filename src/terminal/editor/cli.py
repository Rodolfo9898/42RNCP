"""The command line of `python -m editor_launcher`, and what it wires."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from collections.abc import Mapping

from sandbox.display.xvfb import VirtualDisplay
from terminal.claude.command import ClaudeCommand
from terminal.claude.onboarding import FirstRun
from terminal.editor.claude import ClaudeLauncher
from terminal.editor.extensions import ExtensionList, InstalledExtensions
from terminal.editor.installer import ExtensionInstaller, ExtensionWatcher
from terminal.editor.server import EditorServer
from terminal.environment.child import ChildEnvironment
from terminal.projects.folders import ProjectFolders
from terminal.report.files import ReportFiles
from terminal.settings.settings import Settings


def serve(settings: Settings, environment: ChildEnvironment, display: VirtualDisplay) -> None:
    """Starts VS Code, installs the extensions of the list and keeps it in step with what is installed, and runs the terminal service
    in this process."""
    import uvicorn

    from terminal.api.app import create_app      # (not for `claude`: the web framework is only loaded by the service)

    editor_settings = settings.editor
    server = EditorServer(editor_settings, settings.folders.reports_root, environment)
    server.write_default_settings()
    stop = threading.Event()
    editor = server.start() if server.available() else None
    if editor is None:
        print(f"editor: {editor_settings.server} is missing; only the terminal service runs", file=sys.stderr)
    else:
        installed = InstalledExtensions(editor_settings.extensions)
        installer = ExtensionInstaller(editor_settings, installed, server.environment)
        watcher = ExtensionWatcher(ExtensionList(editor_settings.extensions_list), installed, installer, editor_settings.watch_seconds)
        threading.Thread(target=watcher.keep_in_step, args=(stop,), daemon=True).start()
    try:
        uvicorn.run(create_app(settings, display), host="0.0.0.0", port=editor_settings.service_port)
    finally:
        stop.set()
        if editor is not None and editor.poll() is None:
            os.killpg(editor.pid, signal.SIGTERM)


def main(args: list[str] | None = None, environ: Mapping[str, str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m editor_launcher")
    sub = parser.add_subparsers(dest="command")
    start = sub.add_parser("claude")
    start.add_argument("--session", required=True)
    start.add_argument("--project", required=True)
    start.add_argument("--prompt-file", default="")
    opts = parser.parse_args(args)
    settings = Settings.from_environment(os.environ if environ is None else environ)
    if FirstRun(settings).prepare():
        print("editor: claude's first-run wizard is skipped: the gateway signs it in", file=sys.stderr)
    display = VirtualDisplay()
    environment = ChildEnvironment(settings, display)
    if opts.command == "claude":
        ClaudeLauncher(ProjectFolders(settings.projects), settings.folders, ReportFiles(settings.folders), environment,
                       ClaudeCommand(settings.claude)).start(opts.session, opts.project, opts.prompt_file)
    else:
        serve(settings, environment, display)
