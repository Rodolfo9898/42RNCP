"""Syntax highlighting for the file viewer.

Repository files are untrusted and some lexer regexes can be made pathologically slow, so the
tokenizing happens in a throw-away subprocess (`python -m verdict.highlight`) with a timeout,
a size cap and a line-length cap. The browser only ever receives (class, text) pairs and
builds DOM nodes from them with textContent.
"""

from __future__ import annotations

import json
import subprocess
import sys

MAX_BYTES = 200_000
MAX_LINE = 2_000
TIMEOUT = 6

# Extensions pygments does not know but that belong to a language we meet in 42 projects.
EXTRA_LEXERS = {
    ".tpp": "cpp", ".ipp": "cpp", ".cub": None, ".ft": None,
    ".mk": "make", ".conf": "ini", ".env": "bash", ".tpl": "html",
}
SPECIAL_NAMES = {"makefile": "make", "gnumakefile": "make", "dockerfile": "docker", ".gitignore": "text",
                 ".dockerignore": "text", ".bashrc": "bash", ".zshrc": "bash"}


def _short(token_type) -> str:
    """Collapse pygments' token hierarchy into the handful of classes the stylesheet knows."""
    from pygments.token import Token as T

    checks = [
        (T.Comment.Preproc, "pp"), (T.Comment.PreprocFile, "s"), (T.Comment, "c"),
        (T.Keyword.Type, "ty"), (T.Keyword, "k"), (T.Operator.Word, "k"),
        (T.String, "s"), (T.Number, "n"), (T.Literal, "s"), (T.Escape, "n"),
        (T.Name.Function, "f"), (T.Name.Class, "ty"), (T.Name.Namespace, "ty"), (T.Name.Builtin, "b"),
        (T.Name.Decorator, "pp"), (T.Name.Tag, "k"), (T.Name.Attribute, "v"),
        (T.Name.Constant, "n"), (T.Name.Variable, "v"), (T.Name.Entity, "n"),
        (T.Operator, "o"), (T.Generic.Deleted, "del"), (T.Generic.Inserted, "ins"),
        (T.Generic.Heading, "h"), (T.Generic.Subheading, "h"), (T.Generic.Strong, "h"),
    ]
    for base, name in checks:
        if token_type in base:
            return name
    return ""


def _lexer_for(filename: str, text: str):
    from pygments.lexers import get_lexer_by_name, get_lexer_for_filename, guess_lexer
    from pygments.util import ClassNotFound

    name = filename.rsplit("/", 1)[-1]
    lower = name.lower()
    if lower in SPECIAL_NAMES:
        return get_lexer_by_name(SPECIAL_NAMES[lower])
    ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
    if ext in EXTRA_LEXERS:
        return get_lexer_by_name(EXTRA_LEXERS[ext]) if EXTRA_LEXERS[ext] else None
    try:
        return get_lexer_for_filename(name, text[:5000])
    except ClassNotFound:
        pass
    if text.startswith("#!"):
        try:
            return guess_lexer(text[:5000])
        except ClassNotFound:
            return None
    return None


def tokenize(filename: str, text: str) -> dict | None:
    """Return {"language": str, "lines": [[[cls, text], ...], ...]} or None when not highlightable."""
    if len(text.encode()) > MAX_BYTES or any(len(line) > MAX_LINE for line in text.split("\n")):
        return None
    lexer = _lexer_for(filename, text)
    if lexer is None or lexer.name.lower() in ("text only", "text"):
        return None
    lexer.stripnl = False
    lexer.ensurenl = False
    lines: list[list[list[str]]] = [[]]
    for token_type, value in lexer.get_tokens(text):
        cls = _short(token_type)
        parts = value.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                lines.append([])
            if part:
                current = lines[-1]
                if current and current[-1][0] == cls:
                    current[-1][1] += part
                else:
                    current.append([cls, part])
    expected = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if ["".join(t for _, t in line) for line in lines] != expected:
        return None  # the lexer dropped or invented text: show plain rather than something misleading
    return {"language": lexer.name, "lines": lines}


def highlight(filename: str, text: str) -> dict | None:
    """tokenize() in a subprocess with a timeout; None on any failure."""
    if len(text.encode()) > MAX_BYTES:
        return None
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-m", "verdict.highlight"],
            input=json.dumps({"filename": filename, "text": text}),
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


if __name__ == "__main__":
    request = json.loads(sys.stdin.read())
    json.dump(tokenize(request["filename"], request["text"]), sys.stdout)
