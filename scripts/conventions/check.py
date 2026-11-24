#!/usr/bin/env python3
"""The structure rules of this repository (like the C projects in projects/), checked on Python (and TypeScript) sources.
usage: check.py PATH...        exit code 1 when something breaks a rule (run by tests/infra/test_conventions.py on src/)

  1. no file over 250 lines; no function or method over 40 lines (Python: by ast; TypeScript: by braces, approximately)
  2. no folder with a single module (a package holds at least two modules besides __init__.py), except a package that only has subpackages
  3. a folder holds modules or sub-folders, never both (besides __init__.py, and the extension's main, extension.ts, like the main.c of a C project)
"""
import ast, re, sys
from pathlib import Path

MAX_FILE, MAX_FUNC = 250, 40

def source_files(root):
    return [p for p in sorted(root.rglob("*")) if p.suffix in (".py", ".ts") and "node_modules" not in p.parts and "__pycache__" not in p.parts
            and not p.name.endswith(".d.ts") and "out" not in p.relative_to(root).parts[:1]]

def py_functions(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node.lineno, node.end_lineno - node.lineno + 1

def ts_functions(path):
    lines = path.read_text().split("\n")
    head = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+\w+|(?:public|private|protected|static|readonly|async|get|set|\s)*\w+\s*\([^;]*\)\s*(?::\s*[^={]+)?\{)\s*$|^\s*(?:export\s+)?(?:const|let)\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*[^=]+)?=>\s*\{\s*$")
    i = 0
    while i < len(lines):
        if head.match(lines[i]) and not re.match(r"^\s*(if|for|while|switch|catch|else)\b", lines[i]):
            depth, j = 0, i
            while j < len(lines):
                depth += lines[j].count("{") - lines[j].count("}")
                if depth <= 0 and j >= i:
                    break
                j += 1
            yield lines[i].strip()[:50], i + 1, j - i + 1
        i += 1

def check(root):
    problems = []
    for path in source_files(root):
        n = len(path.read_text().split("\n"))
        if n > MAX_FILE:
            problems.append(f"{path}: {n} lines (max {MAX_FILE})")
        funcs = py_functions(path) if path.suffix == ".py" else ts_functions(path)
        for name, line, length in funcs:
            if length > MAX_FUNC:
                problems.append(f"{path}:{line} {name}: {length} lines (max {MAX_FUNC})")
    for folder in sorted({p.parent for p in source_files(root)} | {d for d in root.rglob("*") if d.is_dir() and "node_modules" not in d.parts and "__pycache__" not in d.parts}):
        if not folder.is_dir() or folder == root:
            continue
        modules = [p for p in folder.iterdir() if p.suffix in (".py", ".ts") and p.name not in ("__init__.py", "extension.ts") and not p.name.endswith(".d.ts")]
        subfolders = [d for d in folder.iterdir() if d.is_dir() and d.name not in ("__pycache__", "node_modules") and any(source_files(d))]
        if len(modules) == 1 and not subfolders:
            problems.append(f"{folder}: a folder with a single module ({modules[0].name})")
        if modules and subfolders:
            problems.append(f"{folder}: holds modules ({len(modules)}) and folders ({len(subfolders)}): put the modules in a folder")
    return problems

if __name__ == "__main__":
    out = [p for arg in sys.argv[1:] for p in check(Path(arg))]
    print("\n".join(out) or "ok: no rule is broken")
    sys.exit(1 if out else 0)
