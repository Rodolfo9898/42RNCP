"""Cloning and browsing untrusted repositories. Nothing here executes repo code."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_BYTES = 1_000_000
MAX_TREE_ENTRIES = 5000
CLONE_TIMEOUT = 300   # a full clone (whole history), not a shallow one

# Accepted forms: git@host:owner/repo(.git)  and  ssh://git@host[:port]/owner/repo(.git)
# Host and user must not start with "-" (ssh would read them as options, e.g. -oProxyCommand=...).
_USER = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
_HOST = r"[A-Za-z0-9][A-Za-z0-9.-]*"
_PATH = r"[\w.~][\w.~/-]*"
SCP_RE = re.compile(rf"^{_USER}@{_HOST}:{_PATH}$")
SSH_RE = re.compile(rf"^ssh://{_USER}@{_HOST}(?::\d{{1,5}})?/{_PATH}$")


class RepoError(ValueError):
    pass


@dataclass
class RepoInfo:
    url: str
    commit: str
    subject: str
    author: str


def validate_url(url: str) -> str:
    url = url.strip()
    if not (SCP_RE.match(url) or SSH_RE.match(url)) or ".." in url:
        raise RepoError("Only SSH repository URLs are accepted, e.g. git@github.com:user/repo.git")
    return url


NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def default_name(url: str) -> str:
    last = re.split(r"[/:]", url.strip().rstrip("/"))[-1]
    last = last[:-4] if last.endswith(".git") else last
    return last if NAME_RE.match(last) else "project"


def resolve_destination(root: Path, destination: str, name: str) -> Path:
    """Where a clone will live: <root>/<destination>/<name>. Never outside `root`, never an existing path."""
    if not NAME_RE.match(name):
        raise RepoError("The project name may only contain letters, digits, '.', '_' and '-' (max 100 characters).")
    destination = destination.strip()
    if destination.startswith(("/", "~")) or "\\" in destination:
        raise RepoError("The destination is a folder inside the projects folder, e.g. 42/common-core (not an absolute path).")
    parts = [p for p in destination.split("/") if p]
    for part in parts:
        if not NAME_RE.match(part):
            raise RepoError(f"Invalid folder name in the destination: {part!r}.")
    root = root.resolve()
    target = root.joinpath(*parts, name)
    if not target.parent.resolve().is_relative_to(root):  # a symlinked folder pointing outside
        raise RepoError("The destination leaves the projects folder.")
    if target.exists() or target.is_symlink():
        raise RepoError(f"{target.relative_to(root).as_posix()} already exists. Choose another name or destination.")
    return target


def clone(url: str, dest: Path, known_hosts: Path) -> RepoInfo:
    """Clone `url` into `dest` (which must not exist). `known_hosts` is where SSH host keys are remembered."""
    url = validate_url(url)
    if dest.exists():
        raise RepoError(f"{dest.name} already exists.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    ssh = (
        "ssh -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new "
        f"-o UserKnownHostsFile={known_hosts}"
    )
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(known_hosts.parent),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_SSH_COMMAND": ssh,
    }
    if os.environ.get("SSH_AUTH_SOCK"):  # the forwarded agent: the private key never enters this container
        env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
    cmd = [
        "git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never",
        "-c", "protocol.ssh.allow=always", "-c", "core.symlinks=true",
        "clone", "--no-recurse-submodules", "--", url, str(dest),          # full history: a real repository with its .git
    ]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=CLONE_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise RepoError(f"git clone timed out after {CLONE_TIMEOUT}s") from exc
    if proc.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)  # safe: resolve_destination guaranteed it did not exist
        raise RepoError(explain_clone_failure(proc.stderr, proc.returncode))
    subprocess.run(["chmod", "-R", "u+rwX", str(dest)], check=False)
    log = subprocess.run(
        ["git", "-C", str(dest), "log", "-1", "--format=%h%n%s%n%an"],
        env=env, capture_output=True, text=True, check=False,
    ).stdout.splitlines() + ["", "", ""]
    return RepoInfo(url=url, commit=log[0], subject=log[1], author=log[2])


def explain_clone_failure(stderr: str, returncode: int) -> str:
    lines = [l.strip() for l in stderr.splitlines() if l.strip() and not l.startswith("Cloning into")]
    message = " | ".join(lines[-4:]) if lines else f"no error output (exit code {returncode})"
    hint = ""
    if "Permission denied (publickey" in stderr or "Could not read from remote repository" in stderr:
        hint = (" — SSH could not authenticate. Check the 'ssh' indicator in the status bar: the container needs your "
                "ssh-agent with a key loaded (run `ssh-add` on your computer), and that key must have access to this repository.")
    elif "Host key verification failed" in stderr:
        hint = " — the host's SSH key is not trusted yet; remove workspace/known_hosts if the server's key changed."
    elif "Could not resolve hostname" in stderr:
        hint = " — the container has no DNS/network access to that host."
    return f"git clone failed: {message}{hint}"


def ssh_status() -> dict:
    """Can this process authenticate over SSH? Explains what is missing when it cannot."""
    sock = os.environ.get("SSH_AUTH_SOCK")
    if not sock:
        return {"ok": False, "code": "no-agent", "keys": [],
                "message": "No ssh-agent is forwarded to the container (SSH_AUTH_SOCK is not set)."}
    if not os.path.exists(sock):
        return {"ok": False, "code": "no-socket", "keys": [],
                "message": f"The agent socket {sock} does not exist. Is an ssh-agent running on your computer? "
                           "(Docker Desktop for Mac forwards it as /run/host-services/ssh-auth.sock.)"}
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "SSH_AUTH_SOCK": sock}
    try:
        proc = subprocess.run(["ssh-add", "-l"], env=env, capture_output=True, text=True, timeout=10)
    except FileNotFoundError:
        return {"ok": False, "code": "no-client", "keys": [], "message": "ssh-add is not installed in the container."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "timeout", "keys": [], "message": "The ssh-agent did not answer within 10 seconds."}
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0:
        keys = [l for l in proc.stdout.splitlines() if l.strip()]
        return {"ok": True, "code": "ok", "keys": keys, "message": f"{len(keys)} key(s) available through the ssh-agent."}
    if proc.returncode == 1:
        return {"ok": False, "code": "no-keys", "keys": [],
                "message": "The ssh-agent is reachable but holds no keys. Run `ssh-add` on your computer, then try again."}
    code = "permission" if "ermission denied" in output else "unreachable"
    return {"ok": False, "code": code, "keys": [],
            "message": f"The container cannot talk to the ssh-agent: {output or 'unknown error'}"}


def list_folders(root: Path, depth: int = 2) -> list[str]:
    """Existing non-repository folders under `root`, as destination suggestions."""
    out: list[str] = []

    def walk(base: Path, prefix: str, level: int) -> None:
        if level > depth or not base.is_dir():
            return
        for child in sorted(base.iterdir()):
            if child.is_dir() and not child.is_symlink() and not (child / ".git").exists() and not child.name.startswith("."):
                rel = f"{prefix}{child.name}"
                out.append(rel)
                walk(child, rel + "/", level + 1)

    walk(root, "", 1)
    return out


def list_existing(root: Path, depth: int = 3) -> list[dict]:
    """Folders under `root` that can be reviewed in place: {"path", "git"}. A git repository is not searched inside."""
    out: list[dict] = []

    def walk(base: Path, prefix: str, level: int) -> None:
        if level > depth or not base.is_dir():
            return
        for child in sorted(base.iterdir()):
            if child.is_symlink() or not child.is_dir() or child.name.startswith(".") or not NAME_RE.match(child.name):
                continue
            rel = f"{prefix}{child.name}"
            is_git = (child / ".git").exists()
            out.append({"path": rel, "git": is_git})
            if not is_git:
                walk(child, rel + "/", level + 1)

    walk(root, "", 1)
    return out


def use_existing(root: Path, rel: str) -> tuple[Path, RepoInfo]:
    """An existing folder inside the projects folder, reviewed where it is (no clone, nothing copied or deleted)."""
    rel = rel.strip().strip("/")
    parts = [p for p in rel.split("/") if p]
    if not parts or rel.startswith("~") or "\\" in rel or not all(NAME_RE.match(p) for p in parts):
        raise RepoError("Choose a folder inside the projects folder, e.g. 42/common-core/push_swap.")
    root = root.resolve()
    path = root.joinpath(*parts)
    if any(root.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1)):
        raise RepoError("That folder is a symbolic link; choose the real folder.")
    if not path.is_dir() or not path.resolve().is_relative_to(root):
        raise RepoError(f"{rel} is not a folder inside the projects folder.")
    return path, _folder_info(path)


def _folder_info(path: Path) -> RepoInfo:
    """Remote, last commit of a folder; empty fields when it is not a git repository."""
    if not (path / ".git").exists():
        return RepoInfo(url="", commit="", subject="", author="")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_TERMINAL_PROMPT": "0"}
    base = ["git", "-c", f"safe.directory={path}", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-C", str(path)]

    def git(*args: str) -> str:
        try:
            return subprocess.run([*base, *args], env=env, capture_output=True, text=True, timeout=20, check=False).stdout
        except (subprocess.TimeoutExpired, OSError):
            return ""

    log = git("log", "-1", "--format=%h%n%s%n%an").splitlines() + ["", "", ""]
    return RepoInfo(url=git("config", "--get", "remote.origin.url").strip(), commit=log[0], subject=log[1], author=log[2])


def safe_path(root: Path, rel: str) -> Path:
    """Resolve `rel` inside `root`; refuse traversal and symlinks that leave the repo."""
    root = root.resolve()
    target = (root / rel).resolve()
    if target != root and not target.is_relative_to(root):
        raise RepoError("path escapes the repository")
    return target


def tracked_files(root: Path) -> list[Path]:
    """Every regular file in the repo (relative paths), ignoring .git and symlinks."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if not path.is_symlink():
                out.append(path.relative_to(root))
    return out


def tree(root: Path) -> list[dict]:
    entries: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        base = Path(dirpath).relative_to(root)
        for d in dirnames:
            entries.append({"path": str(base / d), "type": "dir"})
        for f in sorted(filenames):
            entries.append({"path": str(base / f), "type": "file"})
        if len(entries) > MAX_TREE_ENTRIES:
            break
    return entries[:MAX_TREE_ENTRIES]


def read_text(root: Path, rel: str) -> dict:
    path = safe_path(root, rel)
    if not path.is_file():
        raise RepoError("not a file")
    size = path.stat().st_size
    with path.open("rb") as fh:
        data = fh.read(MAX_FILE_BYTES)
    if b"\0" in data[:8192]:
        return {"path": rel, "binary": True, "size": size, "content": ""}
    return {
        "path": rel, "binary": False, "size": size, "truncated": size > MAX_FILE_BYTES,
        "content": data.decode("utf-8", errors="replace"),
    }
