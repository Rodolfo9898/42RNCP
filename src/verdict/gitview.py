"""What changed in the reviewed project since its last commit (the Source Control view). Read-only: nothing here writes to the repository.

The repository may have been written by someone else, and git runs programs that its own settings name (a filter, a diff driver, an
fsmonitor...). So git only runs here when every setting in .git/config is one we know to be harmless, and with the hooks and the
monitor switched off.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath

from .repo import PULL_SAFE_CONFIG, safe_path

MAX_FILES = 2000
MAX_BYTES = 1_000_000
TIMEOUT = 20

# Settings that only describe how files look or who you are: git runs nothing because of them.
SAFE_CONFIG = re.compile(
    PULL_SAFE_CONFIG.pattern
    + r"|core\.(autocrlf|safecrlf|eol|quotepath|abbrev|untrackedcache|splitindex|trustctime|checkstat|preloadindex|filemode|commentchar)"
    + r"|(?:user|push|pull|fetch|init|color|rebase|rerere|status)\.[a-z0-9.]+|diff\.(?:renames|algorithm|colormoved|mnemonicprefix)"
    + r"|branch\.[^\s]+\.description|remote\.[^\s]+\.push|submodule\.[^\s]+\.(branch|update)",
    re.I,
)


class GitViewError(ValueError):
    pass


def _env() -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C", "GIT_EXTERNAL_DIFF": "", "GIT_ASKPASS": "true"}


def _git(root: Path, *args: str, timeout: float = TIMEOUT, raw: bool = False) -> subprocess.CompletedProcess:
    cmd = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", f"safe.directory={root}", "-c", "core.quotepath=off",
           "-c", "diff.external=", "-c", "protocol.allow=never", "-C", str(root), *args]
    try:
        return subprocess.run(cmd, env=_env(), capture_output=True, text=not raw, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GitViewError(f"git {args[0]} took too long") from exc
    except OSError as exc:
        raise GitViewError(f"git could not be run: {exc}") from exc


def unsafe_settings(root: Path) -> list[str]:
    """The settings of .git/config that git might run something because of (an empty list: it is safe to run git here). The file is read
    from outside the repository (git would fail, or worse, act on a core.worktree before it printed anything) and does not follow
    includes, so an include shows up as a key and is refused. A file that cannot be read is an error, not an empty list."""
    cmd = ["git", "config", "--file", str(root / ".git" / "config"), "--list"]
    try:
        done = subprocess.run(cmd, cwd="/", env=_env(), capture_output=True, text=True, timeout=TIMEOUT, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise GitViewError(f"git could not read .git/config: {exc}") from exc
    if done.returncode != 0:
        raise GitViewError("git could not read .git/config")
    keys = [line.split("=", 1)[0] for line in done.stdout.splitlines() if line]
    return sorted({k for k in keys if not SAFE_CONFIG.fullmatch(k)})


def repository_ok(root: Path) -> str:
    """'' when git can be run in `root`, otherwise why not."""
    if not (root / ".git").is_dir():
        return "This folder is not a git repository."
    try:
        bad = unsafe_settings(root)
    except GitViewError as exc:
        return str(exc)
    if bad:
        return f"Not reading it with git: .git/config has settings that could run commands ({', '.join(bad[:4])})."
    return ""


def status(root: Path) -> dict:
    """{"available", "error", "branch", "head", "upstream", "ahead", "behind", "files": [{path, x, y, kind}]}. x is the state in the index and y
    in the working tree (M modified, A added, D deleted, R renamed, ? not tracked, U conflict)."""
    out = {"available": False, "error": "", "branch": "", "head": "", "upstream": "", "ahead": 0, "behind": 0, "files": [], "truncated": False}
    why = repository_ok(root)
    if why:
        out["error"] = why
        return out
    done = _git(root, "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all", "--ignore-submodules=all", raw=True)
    if done.returncode != 0:
        out["error"] = (done.stderr.decode("utf-8", "replace").strip().splitlines() or ["git status failed"])[-1]
        return out
    out["available"] = True
    records = done.stdout.decode("utf-8", "replace").split("\0")
    skip = False
    for i, record in enumerate(records):
        if skip:
            skip = False
            continue
        if record.startswith("# branch.oid "):
            out["head"] = record[13:20] if record[13:] != "(initial)" else ""
        elif record.startswith("# branch.head "):
            out["branch"] = record[14:]
        elif record.startswith("# branch.upstream "):
            out["upstream"] = record[18:]
        elif record.startswith("# branch.ab "):
            m = re.match(r"# branch\.ab \+(\d+) -(\d+)", record)
            if m:
                out["ahead"], out["behind"] = int(m[1]), int(m[2])
        elif record.startswith("1 "):
            parts = record.split(" ", 8)
            if len(parts) == 9:
                out["files"].append(_entry(parts[8], parts[1]))
        elif record.startswith("2 "):
            parts = record.split(" ", 9)
            if len(parts) == 10:
                entry = _entry(parts[9], parts[1])
                entry["from"] = records[i + 1] if i + 1 < len(records) else ""
                out["files"].append(entry)
            skip = True                                                         # (the old name follows as a record of its own)
        elif record.startswith("u "):
            parts = record.split(" ", 10)
            if len(parts) == 11:
                out["files"].append(_entry(parts[10], "UU"))
        elif record.startswith("? "):
            out["files"].append(_entry(record[2:], "??"))
    out["files"].sort(key=lambda f: (f["path"].count("/"), f["path"]))
    if len(out["files"]) > MAX_FILES:
        out["files"], out["truncated"] = out["files"][:MAX_FILES], True
    return out


def _entry(path: str, xy: str) -> dict:
    x, y = xy[0], xy[1]
    kind = "conflict" if "U" in xy or xy in ("AA", "DD") else "untracked" if xy == "??" else "deleted" if "D" in xy else "added" if "A" in xy else "renamed" if "R" in xy else "modified"
    return {"path": path, "x": x if x != "." else "", "y": y if y != "." else "", "kind": kind}


def _blob(root: Path, spec: str) -> bytes | None:
    """The content of `HEAD:path` (the last commit) or `:path` (the index); None when there is no such entry. The bytes are git's own, as
    stored: no filter or text conversion of the repository is applied."""
    done = _git(root, "cat-file", "blob", spec, raw=True, timeout=10)
    return done.stdout if done.returncode == 0 else None


def _valid_path(path: str | None) -> bool:
    return bool(path) and not path.startswith(("-", "/")) and "\0" not in path and ".." not in path.split("/")


def _working_copy(root: Path, path: str) -> bytes:
    """The file as it is now: nothing when it is gone, where it points when it is a link (what git stores for one). Nothing is read
    from outside the project, and a pipe or a device left in the folder is not opened for reading."""
    rel = PurePosixPath(path)
    try:
        leaf = safe_path(root, str(rel.parent)) / rel.name                      # (the folders on the way are resolved, the file is not)
        if leaf.is_symlink():
            return os.readlink(leaf).encode("utf-8", "surrogateescape")
        fd = os.open(leaf, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return b""
    except (OSError, ValueError) as exc:
        raise GitViewError("the file cannot be read") from exc
    with os.fdopen(fd, "rb") as fh:
        return fh.read(MAX_BYTES + 1) if stat.S_ISREG(os.fstat(fh.fileno()).st_mode) else b""


def sides(root: Path, path: str, staged: bool = False, old: str | None = None) -> dict:
    """The two sides of a change to one file: {"before", "after", "binary", "truncated", "state"}. `staged`: the last commit against the
    index; otherwise the index (the last commit where the file is not staged) against the file now. `old`: where a renamed file was.
    A file that is new has nothing before, a file that is gone has nothing after."""
    why = repository_ok(root)
    if why:
        raise GitViewError(why)
    if not _valid_path(path) or (old is not None and not _valid_path(old)):
        raise GitViewError("not a path of the project")
    head = _blob(root, f"HEAD:{old or path}")
    index = _blob(root, f":{path}")
    if staged:
        before, after = head, index
    else:
        before, after = (index if index is not None else head), _working_copy(root, path)
    before, after = before or b"", after or b""
    binary = b"\0" in before[:8000] or b"\0" in after[:8000]
    truncated = len(before) > MAX_BYTES or len(after) > MAX_BYTES
    text = lambda data: "" if binary else data[:MAX_BYTES].decode("utf-8", "replace")
    return {"path": path, "before": text(before), "after": text(after), "binary": binary, "truncated": truncated,
            "state": "added" if not before and after else "deleted" if before and not after else "modified"}
