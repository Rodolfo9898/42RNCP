"""Cloning and browsing untrusted repositories. Nothing here executes repo code."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
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
    for attempt in range(1 + CLONE_RETRIES):
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=CLONE_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(dest, ignore_errors=True)
            raise RepoError(f"git clone timed out after {CLONE_TIMEOUT}s") from exc
        if proc.returncode == 0:
            break
        shutil.rmtree(dest, ignore_errors=True)  # safe: resolve_destination guaranteed it did not exist
        if attempt < CLONE_RETRIES and is_transient(proc.stderr):
            time.sleep(RETRY_PAUSE)             # a server that answers differently from one connection to the next
            continue
        login = describe_login(probe_login(url, known_hosts, env), url) if SIGN_IN_FAILED in proc.stderr else ""
        raise RepoError(explain_clone_failure(proc.stderr, proc.returncode, login))
    subprocess.run(["chmod", "-R", "u+rwX", str(dest)], check=False)
    log = subprocess.run(
        ["git", "-C", str(dest), "log", "-1", "--format=%h%n%s%n%an"],
        env=env, capture_output=True, text=True, check=False,
    ).stdout.splitlines() + ["", "", ""]
    return RepoInfo(url=url, commit=log[0], subject=log[1], author=log[2])


SIGN_IN_FAILED = "Permission denied (publickey"
CLONE_RETRIES = 1         # one more try when the failure looks like the connection, not like a key that is refused for good
RETRY_PAUSE = 2
TRANSIENT = ("Permission denied (publickey", "Connection closed by", "Connection reset", "kex_exchange_identification",
             "Connection timed out", "Operation timed out")


def is_transient(stderr: str) -> bool:
    return any(sign in stderr for sign in TRANSIENT)


def ssh_target(url: str) -> tuple[str, str, int | None]:
    """(user, host, port) of an address that validate_url accepted."""
    if url.startswith("ssh://"):
        user, _, rest = url[len("ssh://"):].partition("@")
        authority = rest.split("/", 1)[0]
        host, _, port = authority.partition(":")
        return user, host, int(port) if port else None
    user, _, rest = url.partition("@")
    return user, rest.split(":", 1)[0], None


_FINGERPRINT = r"SHA256:[A-Za-z0-9+/]+"
_OFFERED = re.compile(rf"Offering public key: (?P<what>.*?) (?P<fp>{_FINGERPRINT})")
_ACCEPTED = re.compile(rf"Server accepts key: .*?(?P<fp>{_FINGERPRINT})")
_ACCOUNT = re.compile(r"Hi (?P<name>[^!\s]+)!")


def probe_login(url: str, known_hosts: Path, env: dict[str, str]) -> dict | None:
    """Sign in to the server of `url` the way the clone does and report what happened: which keys the ssh-agent offered, which of
    them the server accepted, whether the login worked, and (GitHub) as which account. None when ssh could not be run."""
    user, host, port = ssh_target(url)
    cmd = ["ssh", "-v", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new",
           "-o", f"UserKnownHostsFile={known_hosts}", *(["-p", str(port)] if port else []), f"{user}@{host}"]
    try:
        proc = subprocess.run(cmd, env={k: v for k, v in env.items() if k != "GIT_SSH_COMMAND"}, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    log = f"{proc.stderr}\n{proc.stdout}"
    accepted = {m["fp"] for m in _ACCEPTED.finditer(log)}
    offered, seen = [], set()
    for m in _OFFERED.finditer(log):
        if m["fp"] not in seen:
            seen.add(m["fp"])
            offered.append({"fingerprint": m["fp"], "comment": m["what"].rsplit(" ", 1)[0] if " " in m["what"] else m["what"], "accepted": m["fp"] in accepted})
    account = _ACCOUNT.search(log)
    return {"host": host, "offered": offered, "authenticated": "Authenticated to" in log, "account": account["name"] if account else None}


def describe_login(probe: dict | None, url: str) -> str:
    """What probe_login found, in words (an empty string when there is nothing to add)."""
    if probe is None:
        return ""
    host, offered = probe["host"], probe["offered"]
    if not offered:
        return f"The ssh in the container offered no key to {host} at all: its ssh-agent is empty or cannot be reached (run `make ssh`)."
    keys = ", ".join(f"{k['fingerprint']}" + (f" ({k['comment']})" if k["comment"] else "") for k in offered)
    if probe["authenticated"]:
        who = f" as {probe['account']}" if probe["account"] else ""
        return (f"{host} did accept your key and signed in{who}, so this account cannot read this repository (check its name and that "
                f"{probe['account'] or 'the account'} has access), or the sign-in only failed this time: try again.")
    if any(k["accepted"] for k in offered):
        return (f"{host} knows one of the keys the agent offered, but the agent did not sign with it: {keys}. On your computer, run "
                "`ssh-add -l`, then `ssh-add` the key again (it may be waiting for a passphrase or a confirmation).")
    where = " Compare with the keys on https://github.com/settings/keys." if host == "github.com" else ""
    return (f"{host} accepted none of the {len(offered)} key(s) the ssh-agent offered: {keys}. Add the public key of one of them to your "
            f"account (`ssh-keygen -lf ~/.ssh/<name>.pub` on your computer shows the fingerprint to look for).{where}")


def explain_clone_failure(stderr: str, returncode: int, login: str = "") -> str:
    lines = [l.strip() for l in stderr.splitlines() if l.strip() and not l.startswith("Cloning into")]
    message = " | ".join(lines[-4:]) if lines else f"no error output (exit code {returncode})"
    hint = ""
    if login:
        hint = f" — {login}"
    elif "Permission denied (publickey" in stderr or "Could not read from remote repository" in stderr:
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


# The only settings a repository's own .git/config may hold before it is pulled. claude and the shell can write to the
# projects folder, so anything else (core.sshCommand, core.fsmonitor, a filter driver, an include, ...) could run a command
# here, in the container that has your ssh-agent. A plain clone only has these.
PULL_SAFE_CONFIG = re.compile(
    r"core\.(repositoryformatversion|filemode|bare|logallrefupdates|ignorecase|precomposeunicode|symlinks)"
    r"|remote\.[^\s]+\.(url|fetch|pushurl|prune|tagopt)"
    r"|branch\.[^\s]+\.(remote|merge|rebase)"
    r"|submodule\.[^\s]+\.(url|active)"
    r"|user\.(name|email)|pull\.(rebase|ff)|init\.defaultbranch"
)
PULL_TIMEOUT = 300


def pull(path: Path, known_hosts: Path) -> tuple[RepoInfo, str]:
    """Fast-forward `path` to its upstream (git pull --ff-only), through the ssh-agent. Returns the new state and git's summary."""
    if not (path / ".git").is_dir():
        raise RepoError("This folder is not a git repository, so there is nothing to pull.")
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(known_hosts.parent),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_SSH_COMMAND": ("ssh -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new "
                            f"-o UserKnownHostsFile={known_hosts}"),
    }
    if os.environ.get("SSH_AUTH_SOCK"):
        env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
    base = ["git", "-c", f"safe.directory={path}", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "protocol.allow=never", "-c", "protocol.ssh.allow=always", "-C", str(path)]

    def git(*args: str, timeout: int = 20) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([*base, *args], env=env, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RepoError(f"git {args[0]} timed out after {timeout}s") from exc

    # --local reads only .git/config and does not follow includes, so an include shows up as a key and is refused.
    config = [line.split("=", 1) + [""] for line in git("config", "--local", "--list").stdout.splitlines() if line]
    unsafe = sorted({k for k, *_ in config if not PULL_SAFE_CONFIG.fullmatch(k)})
    if unsafe:
        raise RepoError(f"Not pulling: .git/config has settings that could run commands ({', '.join(unsafe[:5])}). "
                        "Pull from your own terminal after checking them.")
    urls = [v for k, v, *_ in config if re.fullmatch(r"remote\..+\.url", k)]
    if not urls:
        raise RepoError("This repository has no remote to pull from.")
    for url in urls:   # every remote, since the branch may track one other than origin
        validate_url(url)
    proc = git("pull", "--ff-only", "--no-recurse-submodules", timeout=PULL_TIMEOUT)
    if proc.returncode != 0:
        raise RepoError(explain_clone_failure(proc.stderr, proc.returncode).replace("git clone failed", "git pull failed", 1))
    lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    return _folder_info(path), (lines[-1] if lines else "Already up to date.")


# ---------------------------------------------------------------- submodules, fetched for the build

# A project's libs (libft, ft_printf, MiniLibX...) are often submodules that its Makefile downloads with `git submodule update`.
# The sandbox has no network on purpose, so the app downloads them into the disposable copy before the build. The addresses come
# from the project's .gitmodules, which someone else wrote: only these hosts (and the project's own) are contacted, only over
# https without credentials, or over ssh (your agent) to a host on the list, and never a path, `ext::` or `--option`.
SUBMODULE_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org")
MAX_SUBMODULES = 10
SUBMODULE_DEPTH = 2                 # a lib may have libs of its own
SUBMODULE_TIMEOUT = 180             # for one download
SUBMODULE_BUDGET = 420              # for all of them
SUBMODULE_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*){0,3}")
_HTTPS = re.compile(rf"^https://(?P<host>{_HOST})/{_PATH}$")


@dataclass
class SubmoduleNote:
    path: str          # relative to the project
    ok: bool
    message: str       # why it could not be downloaded (or what was done)


def submodule_source(url: str, extra_hosts: frozenset[str] | set[str] = frozenset()) -> str | None:
    """'https' or 'ssh' when `url` is an address a submodule may be downloaded from, None otherwise."""
    allowed = {h.lower() for h in SUBMODULE_HOSTS} | {h.lower() for h in extra_hosts}
    if ".." in url or url.startswith("-"):
        return None
    if (m := _HTTPS.match(url)):
        return "https" if m["host"].lower() in allowed else None
    if SCP_RE.match(url) or SSH_RE.match(url):
        return "ssh" if ssh_target(url)[1].lower() in allowed else None
    return None


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


def _git_in(root: Path, env: dict[str, str], *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", f"safe.directory={root}", "-C", str(root), *args],
                          env=env, capture_output=True, text=True, timeout=timeout, check=False)


def _gitlinks(root: Path, env: dict[str, str]) -> dict[str, str]:
    """path -> the commit the project records for each submodule."""
    out = _git_in(root, env, "-c", "core.quotepath=off", "ls-files", "-s", "-z").stdout
    links = {}
    for record in out.split("\0"):
        meta, _, path = record.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[0] == "160000" and re.fullmatch(r"[0-9a-f]{40}", parts[1]):
            links[path] = parts[1]
    return links


def _module_urls(root: Path, env: dict[str, str]) -> dict[str, str]:
    """path -> url, from .gitmodules."""
    out = _git_in(root, env, "config", "-f", ".gitmodules", "--null", "--list").stdout
    settings: dict[str, dict[str, str]] = {}
    for record in out.split("\0"):
        key, _, value = record.partition("\n")
        if key.startswith("submodule.") and "." in key[len("submodule."):]:
            name, _, var = key[len("submodule."):].rpartition(".")
            settings.setdefault(name, {})[var] = value
    return {v["path"]: v.get("url", "") for v in settings.values() if "path" in v}


def fetch_submodules(root: Path, known_hosts: Path, *, extra_hosts: set[str] | frozenset[str] = frozenset(), protocols: tuple[str, ...] = ("https", "ssh"),
                     allow=submodule_source, budget: float = SUBMODULE_BUDGET, _depth: int = 0, _prefix: str = "", _clock=None) -> list[SubmoduleNote]:
    """Download the submodules of the project in `root` (a disposable copy) at the commits the project records, so that the build
    does not need the network. Never raises. Returns one note per submodule; a folder that already has content is left alone."""
    clock = _clock or time.monotonic
    deadline = clock() + budget
    notes: list[SubmoduleNote] = []
    try:
        known_hosts.parent.mkdir(parents=True, exist_ok=True)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(known_hosts.parent), "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_LFS_SKIP_SMUDGE": "1", "GIT_ALLOW_PROTOCOL": ":".join(protocols),
               "GIT_SSH_COMMAND": f"ssh -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile={known_hosts}"}
        if os.environ.get("SSH_AUTH_SOCK"):
            env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
        links, urls = _gitlinks(root, env), _module_urls(root, env)
    except Exception as exc:
        return [SubmoduleNote("", False, f"could not read the submodules: {exc}")]
    for count, (path, sha) in enumerate(sorted(links.items())):
        shown = f"{_prefix}{path}"
        if count >= MAX_SUBMODULES:
            notes.append(SubmoduleNote(shown, False, f"more than {MAX_SUBMODULES} submodules: this one was not downloaded"))
            continue
        try:
            notes.append(_fetch_one(root, path, sha, urls.get(path, ""), shown, env, extra_hosts, protocols, allow, deadline, clock))
        except Exception as exc:
            notes.append(SubmoduleNote(shown, False, f"{type(exc).__name__}: {exc}"))
        if notes[-1].ok and _depth + 1 < SUBMODULE_DEPTH and (root / path / ".gitmodules").is_file():
            notes += fetch_submodules(root / path, known_hosts, extra_hosts=extra_hosts, protocols=protocols, allow=allow,
                                      budget=max(0.0, deadline - clock()), _depth=_depth + 1, _prefix=f"{shown}/", _clock=clock)
    return notes


def _fetch_one(root: Path, path: str, sha: str, url: str, shown: str, env: dict[str, str], extra_hosts, protocols, allow, deadline: float, clock) -> SubmoduleNote:
    if not SUBMODULE_PATH.fullmatch(path) or ".git" in path.split("/"):
        return SubmoduleNote(shown, False, "its folder name is not one this app will write to")
    dest = root / path
    if not dest.parent.resolve().is_relative_to(root.resolve()) or dest.is_symlink():
        return SubmoduleNote(shown, False, "its folder is a link or leaves the project")
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        return SubmoduleNote(shown, True, "already there")
    if not url:
        return SubmoduleNote(shown, False, ".gitmodules gives no address for it")
    source = allow(url, extra_hosts)
    if source is None:
        return SubmoduleNote(shown, False, f"{url} is not an address this app downloads from (github.com, gitlab.com, bitbucket.org, codeberg.org, or the project's own host)")
    if source == "ssh" and not env.get("SSH_AUTH_SOCK"):
        return SubmoduleNote(shown, False, f"{url} needs your ssh-agent, which is not available")
    attempts = [url]
    if source == "https" and env.get("SSH_AUTH_SOCK") and (m := _HTTPS.match(url)) and m["host"].lower() == "github.com":
        attempts.append("git@github.com:" + url[len("https://github.com/"):])        # a private repository: the same repository, through your agent
    config = ["-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never", "-c", "credential.helper=",
              *(a for proto in protocols for a in ("-c", f"protocol.{proto}.allow=always"))]
    last = ""
    for address in attempts:
        left = deadline - clock()
        if left <= 1:
            return SubmoduleNote(shown, False, "ran out of time downloading submodules")
        dest.mkdir(parents=True, exist_ok=True)
        try:
            done = subprocess.run(["git", *config, "clone", "-q", "--no-recurse-submodules", "--", address, str(dest)], env=env, capture_output=True,
                                  text=True, timeout=min(SUBMODULE_TIMEOUT, left), check=False)
        except subprocess.TimeoutExpired:
            last = "the download timed out"
            _empty(dest)
            continue
        if done.returncode == 0:
            last = ""
            break
        last = (done.stderr.strip().splitlines() or ["git clone failed"])[-1]
        _empty(dest)
    if last:
        return SubmoduleNote(shown, False, last)
    checkout = _git_in(dest, env, "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", sha, timeout=60)
    if checkout.returncode != 0:                                                            # a commit that is not on a branch the clone fetched
        _git_in(dest, env, "fetch", "-q", "origin", sha, timeout=min(SUBMODULE_TIMEOUT, max(1.0, deadline - clock())))
        checkout = _git_in(dest, env, "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", sha, timeout=60)
    if checkout.returncode != 0:
        return SubmoduleNote(shown, False, f"downloaded, but the commit {sha[:7]} the project records is not in it")
    return SubmoduleNote(shown, True, f"downloaded at {sha[:7]}")


def _empty(folder: Path) -> None:
    """Back to the empty folder it was: what a failed download left behind goes."""
    for child in folder.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


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
