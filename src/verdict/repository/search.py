"""Find text in the files of the reviewed project (the Search view). Read-only: nothing here runs repository code.

A literal search runs in this process. A regular expression is written by the user and could backtrack for ever, so it runs in a
separate Python (`python -I search.py`, a script that needs nothing but the standard library) that is killed when it takes too long.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_QUERY = 200
MAX_FILE_BYTES = 1_000_000          # as much of a file as the file viewer shows
MAX_FILES = 6000
MAX_MATCHES = 2000
MAX_PER_FILE = 200
MAX_PER_LINE = 20
PREVIEW = 240                       # characters of a matching line that are sent back
REGEX_SECONDS = 6


def _body(pattern: str) -> str:
    """The regular expression for a glob, without the 'any depth' prefix and the 'everything inside' suffix."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "{" and (end := pattern.find("}", i)) > i:                  # {c,h}
            out.append("(?:" + "|".join(_body(part) for part in pattern[i + 1:end].split(",")) + ")")
            i = end + 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def glob_regex(pattern: str) -> re.Pattern:
    """A VS Code style glob: `*` and `?` stay inside a folder name, `**` crosses folders, `{c,h}` is either, a pattern without `/`
    matches at any depth, and a folder matches everything in it. Matched against the path relative to the project."""
    pattern = pattern.strip()
    while pattern.startswith("./"):
        pattern = pattern[2:]
    folder_only = pattern.endswith("/")
    pattern = pattern.rstrip("/")
    prefix = "(?:.*/)?" if "/" not in pattern else ""
    return re.compile(f"{prefix}{_body(pattern)}" + ("/.*" if folder_only else "(?:/.*)?"), re.S)


def split_globs(text: str) -> list[str]:
    """The comma separated patterns of "files to include": a comma inside {a,b} belongs to the pattern."""
    parts, depth, current = [], 0, ""
    for c in text:
        depth += (c == "{") - (c == "}" and depth > 0)
        if c == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += c
    return [p for p in parts + [current] if p.strip()]


def globs(text: str) -> list[re.Pattern]:
    return [glob_regex(part) for part in split_globs(text)][:20]


def compile_query(query: str, *, case: bool, word: bool, regex: bool) -> re.Pattern:
    if not query or len(query) > MAX_QUERY:
        raise ValueError(f"the search text must be between 1 and {MAX_QUERY} characters")
    source = query if regex else re.escape(query)
    if word:
        source = rf"(?<!\w)(?:{source})(?!\w)"
    try:
        return re.compile(source, 0 if case else re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"not a valid regular expression: {exc}") from exc


def files_of(root: Path) -> list[Path]:
    """Every regular file of the project (relative paths) except what is inside .git; links are not followed."""
    out: list[Path] = []
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(names):
            path = Path(folder) / name
            if not path.is_symlink():
                out.append(path.relative_to(root))
            if len(out) >= MAX_FILES:
                return out
    return out


def search(root: Path, query: str, *, case: bool = False, word: bool = False, regex: bool = False,
           include: str = "", exclude: str = "") -> dict:
    pattern = compile_query(query, case=case, word=word, regex=regex)
    wanted, unwanted = globs(include), globs(exclude)
    files, total, truncated = [], 0, False
    for rel in files_of(root):
        posix = rel.as_posix()
        if (wanted and not any(g.fullmatch(posix) for g in wanted)) or any(g.fullmatch(posix) for g in unwanted):
            continue
        try:
            with (root / rel).open("rb") as fh:
                data = fh.read(MAX_FILE_BYTES)
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue                                         # a binary file
        matches = []
        for number, line in enumerate(data.decode("utf-8", errors="replace").split("\n"), 1):
            if len(line) > 4000:
                line = line[:4000]                           # (a minified file: the part that is looked at is bounded)
            count = 0
            for found in pattern.finditer(line):
                if found.end() == found.start():
                    continue
                start = max(0, found.start() - 60) if found.start() > PREVIEW - 80 else 0
                matches.append({"line": number, "col": found.start(), "length": found.end() - found.start(),
                                "preview": line[start:start + PREVIEW], "preview_start": start})
                count += 1
                if count >= MAX_PER_LINE or len(matches) >= MAX_PER_FILE or total + len(matches) >= MAX_MATCHES:
                    break
            if len(matches) >= MAX_PER_FILE or total + len(matches) >= MAX_MATCHES:
                truncated = True
                break
        if matches:
            files.append({"path": posix, "matches": matches})
            total += len(matches)
        if total >= MAX_MATCHES:
            truncated = True
            break
    return {"files": files, "total": total, "truncated": truncated, "error": ""}


def search_safely(root: Path, query: str, *, case: bool = False, word: bool = False, regex: bool = False,
                  include: str = "", exclude: str = "", seconds: float = REGEX_SECONDS) -> dict:
    """search(), except that a regular expression runs in a child process that is given `seconds` to answer."""
    options = {"case": case, "word": word, "regex": regex, "include": include, "exclude": exclude}
    if not regex:
        try:
            return search(root, query, **options)
        except ValueError as exc:
            return {"files": [], "total": 0, "truncated": False, "error": str(exc)}
    request = json.dumps({"root": str(root), "query": query, **options})
    try:
        done = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve())], input=request, capture_output=True, text=True,
                              timeout=seconds, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONDONTWRITEBYTECODE": "1"})
    except subprocess.TimeoutExpired:
        return {"files": [], "total": 0, "truncated": False, "error": "The search took too long and was stopped (a pattern that backtracks a lot?)."}
    try:
        return json.loads(done.stdout)
    except ValueError:
        return {"files": [], "total": 0, "truncated": False, "error": "The search failed."}


if __name__ == "__main__":
    asked = json.loads(sys.stdin.read())
    try:
        answer = search(Path(asked.pop("root")), asked.pop("query"), **asked)
    except ValueError as exc:
        answer = {"files": [], "total": 0, "truncated": False, "error": str(exc)}
    sys.stdout.write(json.dumps(answer))
