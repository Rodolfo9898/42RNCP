"""Suggestions for making a project better: structure, code, logic and readability.

Everything here is a heuristic read of the files. It never affects the verdict, and the
logic findings are worded as "possible" because a script cannot prove a bug.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

from .checks import Ctx, strip_code
from .models import Evidence, Improvement

LONG_FUNCTION = 40
LONG_FILE = 500
LONG_LINE = 120
MAX_NESTING = 5
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _ev(file: Path | str, line: int | None = None, snippet: str = "") -> Evidence:
    return Evidence(file=str(file), line=line, snippet=snippet[:160])


# --------------------------------------------------------------------------- structure


def readme_status(ctx: Ctx) -> dict:
    root = [p for p in ctx.files() if len(p.parts) == 1]
    found = next((p for p in root if p.name == "README.md"), None) or next((p for p in root if p.name.lower().startswith("readme")), None)
    if not found:
        return {"present": False, "name": None, "lines": 0}
    return {"present": True, "name": found.name, "lines": len([l for l in ctx.read(found).splitlines() if l.strip()])}


def readme_required(ctx: Ctx) -> bool:
    """Common-core subjects dictate the README's content; later projects leave it free."""
    return any(r.kind == "readme" for r in ctx.rules)


def structure(ctx: Ctx) -> Iterable[Improvement]:
    status = readme_status(ctx)
    required = readme_required(ctx)
    if not status["present"]:
        if required:
            yield Improvement(
                category="structure", priority="high", title="No README found",
                detail="The subject requires a README.md at the root: the first line in italics (*This project has been created "
                       "as part of the 42 curriculum by <login>*), then Description, Instructions (how to build and run) and "
                       "Resources (references, and how AI was used).")
        else:
            yield Improvement(
                category="structure", priority="medium", title="No README found",
                detail="None of the loaded subjects requires one, but a README is the best guide to a project: what it does, how to "
                       "build and run it, how the code is organised and why the main design choices were made. Anyone reading "
                       "the repository (a reviewer, or you in six months) will start there.")
    elif status["name"] != "README.md":
        yield Improvement(category="structure", priority="medium" if required else "low", title=f"Rename {status['name']} to README.md",
                          detail="A file named exactly README.md is shown automatically by Git hosting sites"
                                 + (" and the subject requires that name." if required else "."))
    elif status["lines"] < 12:
        yield Improvement(category="structure", priority="low", title="README is very short",
                          detail=f"Only {status['lines']} non-empty lines. Treat it as a guide to the project: explain the goal, how "
                                 "to compile and run it, how the code is organised, and give a usage example.",
                          evidence=[_ev("README.md", 1)])

    files = ctx.files()
    sources = [p for p in ctx.source_files() if len(p.parts) == 1]
    if not any(p.name == ".gitignore" for p in files if len(p.parts) == 1):
        yield Improvement(category="structure", priority="medium", title="No .gitignore",
                          detail="Add one so object files, binaries and editor files are never committed.")
    if len(sources) > 8 and not any(p.parts[0] in ("src", "srcs", "sources") for p in files if len(p.parts) > 1):
        yield Improvement(category="structure", priority="low", title="All sources are at the repository root",
                          detail=f"{len(sources)} source/header files sit next to the Makefile. Group them (for example "
                                 "src/ for .c files and include/ for headers) unless the subject says to keep them at the root.")
    leftovers = [p for p in files if re.search(r"(~|\.bak|\.orig|\.swp|\.tmp)$", p.name)
                 or p.name in ("a.out", "core", "nohup.out") or re.fullmatch(r"(test|tmp|old|copy)\w*\.(c|cpp|h)", p.name, re.I)]
    if leftovers:
        yield Improvement(category="structure", priority="low", title="Leftover or scratch files",
                          detail="These look like experiments or backups; remove them or move them out of the repository.",
                          evidence=[_ev(p) for p in leftovers[:10]])

    for makefile in (p for p in files if p.name == "Makefile" and not any("mlx" in part.lower() for part in p.parts)):
        text = ctx.read(makefile)
        lines = text.splitlines()
        wild = [(i + 1, l) for i, l in enumerate(lines) if re.search(r"\$\(wildcard|\bSRCS?\s*[:+]?=.*\*\.c", l)]
        if wild:
            yield Improvement(category="structure", priority="medium", title="Makefile finds sources with a wildcard",
                              detail="42 projects must list source files explicitly so that adding a file never silently changes the build.",
                              evidence=[_ev(makefile, n, l.strip()) for n, l in wild[:5]])
        if ".PHONY" not in text:
            yield Improvement(category="structure", priority="low", title="Makefile has no .PHONY line",
                              detail="Declare all, clean, fclean and re as .PHONY so a file with the same name never blocks them.",
                              evidence=[_ev(makefile)])


# --------------------------------------------------------------------------- code & readability


def functions(code: str) -> Iterable[tuple[str, int, int]]:
    """(name, first line, last line) of function definitions in comment-free C-like code."""
    lines = code.split("\n")
    depth = 0
    start = None
    name = ""
    previous_signature = ""
    for number, line in enumerate(lines, 1):
        opens, closes = line.count("{"), line.count("}")
        if depth == 0 and opens:
            signature = line if ")" in line.split("{")[0] else previous_signature
            if re.search(r"\)\s*(const\s*)?$", signature.split("{")[0].rstrip()) and not re.match(r"\s*(struct|enum|union|typedef|namespace|class)\b", signature):
                m = list(re.finditer(r"([~\w:]+)\s*\(", signature))
                name = m[0].group(1) if m else "?"
                start = number
        depth += opens - closes
        if depth == 0 and start is not None and closes:
            yield name, start, number
            start = None
        if line.strip():
            previous_signature = line if depth == 0 else previous_signature


def code_and_readability(ctx: Ctx) -> Iterable[Improvement]:
    sources = ctx.source_files()
    long_functions: list[tuple[int, str, str, int]] = []
    long_files: list[tuple[int, str]] = []
    deep: list[Evidence] = []
    long_lines: list[Evidence] = []
    debug: list[Evidence] = []
    unsafe: list[Evidence] = []
    commented_code: list[Evidence] = []
    todo: list[Evidence] = []
    for rel in sources:
        raw = ctx.read(rel)
        raw_lines = raw.splitlines()
        if len(raw_lines) > LONG_FILE:
            long_files.append((len(raw_lines), rel.as_posix()))
        code = strip_code(raw)
        for name, first, last in functions(code):
            body = last - first - 1
            if body > LONG_FUNCTION:
                long_functions.append((body, name, rel.as_posix(), first))
        for number, (raw_line, code_line) in enumerate(zip(raw_lines, code.split("\n")), 1):
            expanded = raw_line.expandtabs(4)
            if len(expanded) > LONG_LINE and ctx.lang == "cpp" and len(long_lines) < 10:
                long_lines.append(_ev(rel, number, f"{len(expanded)} columns"))
            indent = len(raw_line) - len(raw_line.lstrip("\t"))
            if code_line.strip() and indent > MAX_NESTING and len(deep) < 10:
                deep.append(_ev(rel, number, raw_line.strip()))
            if re.search(r"printf\s*\(\s*\"\s*(\[?debug|here|test|\w*\bDEBUG)", raw_line, re.I) and len(debug) < 10:
                debug.append(_ev(rel, number, raw_line.strip()))
            if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", raw_line) and len(todo) < 10:
                todo.append(_ev(rel, number, raw_line.strip()))
            if re.match(r"\s*//\s*(\w+\s*\(.*\)\s*;|[\w\->.\[\]]+\s*=\s*.+;|\}|\{|if\s*\(|while\s*\(|return\b.*;)\s*$", raw_line) and len(commented_code) < 10:
                commented_code.append(_ev(rel, number, raw_line.strip()))
            if rel.suffix in (".c", ".h") and re.search(r"(?<![\w.>])(gets|strcpy|strcat|sprintf|system)\s*\(", code_line) and len(unsafe) < 10:
                unsafe.append(_ev(rel, number, raw_line.strip()))

    if long_functions:
        long_functions.sort(reverse=True)
        yield Improvement(category="readability", priority="medium", title=f"{len(long_functions)} very long function(s)",
                          detail=f"Functions longer than {LONG_FUNCTION} lines are hard to read and test. Split them into small helpers "
                                 "that each do one thing (the Norm already limits C functions to 25 lines).",
                          evidence=[_ev(f, line, f"{name}(): {size} lines") for size, name, f, line in long_functions[:8]])
    if long_files:
        long_files.sort(reverse=True)
        yield Improvement(category="structure", priority="low", title="Very long source files",
                          detail=f"Files over {LONG_FILE} lines usually mix several responsibilities; split them by topic.",
                          evidence=[_ev(f, snippet=f"{n} lines") for n, f in long_files[:6]])
    if deep:
        yield Improvement(category="readability", priority="medium", title="Deeply nested code",
                          detail=f"More than {MAX_NESTING} levels of indentation. Return early, or move the inner block into a function.",
                          evidence=deep)
    if long_lines:
        yield Improvement(category="readability", priority="low", title="Very long lines",
                          detail=f"Lines wider than {LONG_LINE} columns are hard to review.", evidence=long_lines)
    if debug:
        yield Improvement(category="code", priority="medium", title="Debug output left in the code",
                          detail="Remove debugging prints (or hide them behind a macro) before submitting.", evidence=debug)
    if commented_code:
        yield Improvement(category="code", priority="low", title="Commented-out code",
                          detail="Delete dead code instead of commenting it out; git remembers it.", evidence=commented_code)
    if todo:
        yield Improvement(category="code", priority="low", title="Unresolved TODO/FIXME notes", detail="", evidence=todo)
    if unsafe:
        yield Improvement(category="code", priority="medium", title="Functions that are easy to misuse",
                          detail="gets, strcpy, strcat and sprintf do no bounds checking and system() runs a shell. "
                                 "Use sized alternatives (or your own checked helpers), and check whether the subject allows them at all.",
                          evidence=unsafe)


# --------------------------------------------------------------------------- logic

ALLOC = re.compile(r"(?:^|[^\w])(\w+)\s*=\s*(?:\([^)]*\)\s*)?(?:malloc|calloc|realloc|ft_calloc|strdup|ft_strdup|ft_substr|ft_strjoin|ft_split)\s*\(")
OPEN = re.compile(r"(?:^|[^\w])(\w+)\s*=\s*open\s*\(")


def _checked(var: str, following: list[str]) -> bool:
    pattern = re.compile(rf"(!\s*\(?\s*{re.escape(var)}\b|\b{re.escape(var)}\s*(==|<|<=)\s*(NULL|0|-1|nullptr)\b|\b(NULL|0|-1)\s*(==|>)\s*{re.escape(var)}\b|\bif\s*\(\s*{re.escape(var)}\s*\)|\b{re.escape(var)}\s*\?)")
    return any(pattern.search(line) for line in following)


def logic(ctx: Ctx) -> Iterable[Improvement]:
    unchecked_alloc: list[Evidence] = []
    unchecked_open: list[Evidence] = []
    for rel in ctx.source_files():
        if rel.suffix not in (".c", ".cpp", ".cc"):
            continue
        raw_lines = ctx.read(rel).splitlines()
        code_lines = strip_code("\n".join(raw_lines)).split("\n")
        for index, line in enumerate(code_lines):
            window = code_lines[index + 1:index + 6]
            m = ALLOC.search(line)
            if m and not _checked(m.group(1), window) and len(unchecked_alloc) < 12:
                unchecked_alloc.append(_ev(rel, index + 1, raw_lines[index].strip()))
            m = OPEN.search(line)
            if m and not _checked(m.group(1), window) and len(unchecked_open) < 12:
                unchecked_open.append(_ev(rel, index + 1, raw_lines[index].strip()))
    if unchecked_alloc:
        yield Improvement(category="logic", priority="high", title="Possible unchecked allocation",
                          detail="These allocations are not followed by a NULL check within a few lines. A failed malloc would "
                                 "crash with a segfault; check the result and free what was already allocated before returning.",
                          evidence=unchecked_alloc)
    if unchecked_open:
        yield Improvement(category="logic", priority="medium", title="Possible unchecked open()",
                          detail="open() returns -1 on failure; the result is not compared within a few lines.", evidence=unchecked_open)


CHECKS: tuple[Callable[[Ctx], Iterable[Improvement]], ...] = (structure, code_and_readability, logic)


def suggest(ctx: Ctx) -> list[Improvement]:
    out: list[Improvement] = []
    for check in CHECKS:
        try:
            out.extend(check(ctx))
        except Exception as exc:  # one broken heuristic must not hide the others
            out.append(Improvement(category="code", priority="low", title=f"Analysis step {check.__name__} failed", detail=f"{type(exc).__name__}: {exc}"))
    out.sort(key=lambda i: PRIORITY_ORDER[i.priority])
    return out
