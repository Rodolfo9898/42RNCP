"""The editor: VS Code in the browser (OpenVSCode Server), in the `terminal` container next to claude and the toolchain.

    python -m verdict.editor                 start VS Code, install the extensions of config/extensions.txt, keep that list in step
                                             with what is installed, and run the terminal service (verdict.terminal) in this process
    python -m verdict.editor claude --session SID --project DIR --prompt-file FILE
                                             claude, started by the Verdict extension in a VS Code terminal with the review prompt

The extensions are VS Code's own (from Open VSX). config/extensions.txt is the list: one id per line (publisher.name), `#` starts
a comment. When the container starts, every extension of the list that is not installed yet is installed. While it runs, an
extension installed from the Extensions view is added to the list and one uninstalled is taken off it, so the next start (after
`make fclean`, on another machine) installs the same set again by itself. An id that could not be installed (no network) stays.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

SERVER = Path(os.environ.get("OPENVSCODE_SERVER", "/opt/openvscode-server/bin/openvscode-server"))
HOME = Path(os.environ.get("TERMINAL_HOME", "/home/term"))
DATA = Path(os.environ.get("EDITOR_DATA_DIR", str(HOME / ".openvscode-server")))
EXTENSIONS = DATA / "extensions"
LIST = Path(os.environ.get("EDITOR_EXTENSIONS_LIST", "/config/extensions.txt"))
DEFAULTS = Path(os.environ.get("EDITOR_DEFAULT_SETTINGS", "/etc/verdict-editor/settings.json"))
PORT = os.environ.get("EDITOR_PORT", "3000")
FOLDER = os.environ.get("PROJECTS_DIR", "/projects")
WATCH_SECONDS = 10
EXTENSION_ID = re.compile(r"[A-Za-z0-9][\w-]*\.[A-Za-z0-9][\w.-]*")
HEADER = ("# VS Code extensions (Open VSX ids, publisher.name), installed when the editor starts if they are not already.\n"
          "# An extension you install or uninstall in the editor is added here or taken off by itself. `#` starts a comment.\n")


# --------------------------------------------------------------------------- the list of extensions


def read_list(path: Path = LIST) -> list[str]:
    """The ids of the list, in order, lower-cased, without comments, blank lines or anything that is not an id."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    ids: list[str] = []
    for line in lines:
        word = line.split("#", 1)[0].strip().lower()
        if EXTENSION_ID.fullmatch(word) and word not in ids:
            ids.append(word)
    return ids


def write_list(ids: list[str], path: Path = LIST) -> None:
    """The list with these ids, sorted, under the comments the file starts with (or the usual header). Written in place: the file
    is a bind mount of config/extensions.txt, which a rename into it would replace by a file the host never sees."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    head = "".join(line + "\n" for line in text.splitlines() if line.startswith("#")) or HEADER
    with open(path, "w", encoding="utf-8") as out:
        out.write(head + "".join(f"{i}\n" for i in sorted(set(ids))))


def installed(folder: Path | None = None) -> set[str]:
    """The ids of the extensions installed in `folder` (the editor's), from the manifest VS Code keeps there (extensions.json)."""
    folder = EXTENSIONS if folder is None else folder
    try:
        entries = json.loads((folder / "extensions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    ids = set()
    for entry in entries if isinstance(entries, list) else []:
        ident = (entry.get("identifier") or {}).get("id") if isinstance(entry, dict) else None
        if isinstance(ident, str) and EXTENSION_ID.fullmatch(ident):
            ids.add(ident.lower())
    return ids


def install_missing(ids: list[str], run=subprocess.run) -> list[str]:
    """Installs each id that is not installed yet. Returns the ids that could not be installed."""
    have = installed()
    failed = []
    for ident in ids:
        if ident in have:
            continue
        done = run([str(SERVER), "--extensions-dir", str(EXTENSIONS), "--install-extension", ident],
                   capture_output=True, text=True, timeout=300, env=server_env())
        if done.returncode != 0:
            failed.append(ident)
            print(f"editor: could not install {ident}: {(done.stderr or done.stdout).strip()[-300:]}", file=sys.stderr)
        else:
            print(f"editor: installed {ident}")
    return failed


def sync(before: set[str], now: set[str], path: Path = LIST) -> bool:
    """What changed between two looks at the installed extensions goes into the list: one installed meanwhile is added, one
    uninstalled is taken off. Ids that were never installed (an install that failed) are left alone. True when it wrote."""
    added, removed = now - before, before - now
    if not added and not removed:
        return False
    listed = read_list(path)
    wanted = [i for i in listed if i not in removed] + sorted(i for i in added if i not in listed)
    if wanted == listed:
        return False
    write_list(wanted, path)
    return True


def keep_list_in_step(stop: threading.Event) -> None:
    """Installs what the list asks for, then follows what is installed and uninstalled for as long as the editor runs."""
    if LIST.parent.is_dir() and not LIST.exists():
        write_list([])
    install_missing(read_list())
    seen = installed()
    while not stop.wait(WATCH_SECONDS):
        now = installed()
        try:
            sync(seen, now)
        except OSError as exc:
            print(f"editor: could not update {LIST}: {exc}", file=sys.stderr)
            continue
        seen = now


# --------------------------------------------------------------------------- VS Code


def server_env() -> dict[str, str]:
    """What VS Code, and every terminal opened in it, gets: claude's environment (no token, no secret of the service), a shell,
    the address of the web app for the Verdict extension, and git allowed in the projects folder (it belongs to your user on the
    host, which git inside a container may see as someone else)."""
    from .terminal import child_env

    env = child_env()
    env.update(SHELL=os.environ.get("TERMINAL_SHELL", "/bin/bash"), VERDICT_API=os.environ.get("VERDICT_API", "http://web:8000"),
               GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0="*")
    if os.environ.get("ZDOTDIR"):
        env["ZDOTDIR"] = os.environ["ZDOTDIR"]
    return env


def default_settings() -> None:
    """The settings the editor starts with (machine level: what you change in Settings wins over them)."""
    machine = DATA / "data" / "Machine"
    try:
        machine.mkdir(parents=True, exist_ok=True)
        (machine / "settings.json").write_text(DEFAULTS.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError as exc:
        print(f"editor: default settings not written: {exc}", file=sys.stderr)


def token_file() -> Path | None:
    """The connection token, in a file only this user reads: the browser must open the editor with ?tkn=<it> once."""
    token = os.environ.get("EDITOR_TOKEN", "").strip()
    if not token:
        return None
    path = Path("/tmp/editor-token")
    path.write_text(token, encoding="utf-8")
    path.chmod(0o600)
    return path


def start_server() -> subprocess.Popen:
    token = token_file()
    argv = [str(SERVER), "--host", "0.0.0.0", "--port", PORT, "--server-data-dir", str(DATA), "--extensions-dir", str(EXTENSIONS),
            "--default-folder", FOLDER, "--telemetry-level", "off"]
    argv += ["--connection-token-file", str(token)] if token else ["--without-connection-token"]
    return subprocess.Popen(argv, env=server_env(), start_new_session=True)


def serve() -> None:
    import uvicorn

    default_settings()
    stop = threading.Event()
    editor = start_server() if SERVER.exists() else None
    if editor is None:
        print(f"editor: {SERVER} is missing; only the terminal service runs", file=sys.stderr)
    else:
        threading.Thread(target=keep_list_in_step, args=(stop,), daemon=True).start()
    try:
        uvicorn.run("verdict.terminal:app", host="0.0.0.0", port=8002)
    finally:
        stop.set()
        if editor is not None and editor.poll() is None:
            os.killpg(editor.pid, signal.SIGTERM)


# --------------------------------------------------------------------------- claude, from the Verdict extension


def claude(session: str, project: str, prompt_file: str) -> None:
    """Replaces this process by claude, in the project folder, with the review prompt and the environment of a review: where the
    subject PDFs are, where its report goes (outside the project), and nothing else."""
    from .terminal import PROJECTS, SESSION_ID, child_env, interactive_argv

    folder = Path(project).resolve()
    if not SESSION_ID.fullmatch(session) or not folder.is_dir() or not folder.is_relative_to(PROJECTS.resolve()):
        sys.exit(f"verdict: not a review of a project in {PROJECTS}: {session!r} {project!r}")
    prompt = None
    if prompt_file:
        path = Path(prompt_file)
        try:
            prompt = path.read_text(encoding="utf-8")
        finally:
            path.unlink(missing_ok=True)
    env = child_env(session, folder)
    (Path(env["REPORT_DIR"])).mkdir(parents=True, exist_ok=True)
    os.chdir(folder)
    argv = interactive_argv(prompt, live=True)
    os.execvpe(argv[0], argv, env)


def main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m verdict.editor")
    sub = parser.add_subparsers(dest="command")
    start = sub.add_parser("claude")
    start.add_argument("--session", required=True)
    start.add_argument("--project", required=True)
    start.add_argument("--prompt-file", default="")
    opts = parser.parse_args(args)
    if opts.command == "claude":
        claude(opts.session, opts.project, opts.prompt_file)
    else:
        serve()


if __name__ == "__main__":
    main()
