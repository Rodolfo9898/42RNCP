"""Checks that only read files; they never need the sandbox."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from ..models import CheckResult, Evidence, Rule
from ..sandbox import SandboxError
from . import PHASE_STATIC, Ctx, checker, grep, label, result

BINARY_MAGIC = (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"MZ")
ARTIFACT_SUFFIXES = {".o", ".a", ".so", ".dylib", ".out", ".exe"}
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "API key"),
]
SECRET_FILENAMES = {".env", "id_rsa", "id_ed25519", ".npmrc", ".pypirc"}


def repo_hygiene(ctx: Ctx) -> Iterable[CheckResult]:
    artifacts: list[Evidence] = []
    secrets: list[Evidence] = []
    scanned = 0
    for rel in ctx.files():
        posix = rel.as_posix()
        if ctx.is_vendored(posix):
            continue
        path = ctx.repo / rel
        try:
            head = path.open("rb").read(4)
        except OSError:
            continue
        if rel.suffix in ARTIFACT_SUFFIXES or rel.name == ".DS_Store" or any(head.startswith(m) for m in BINARY_MAGIC):
            artifacts.append(Evidence(file=posix, snippet="compiled or system file committed"))
        if rel.name in SECRET_FILENAMES or rel.suffix in (".pem", ".key"):
            secrets.append(Evidence(file=posix, snippet="file usually holds credentials"))
        if scanned < 4000 and path.stat().st_size < 500_000 and head[:1] != b"\x7f":
            scanned += 1
            text = ctx.read(rel)
            for pattern, kind in SECRET_PATTERNS:
                m = pattern.search(text)
                if m:
                    line = text.count("\n", 0, m.start()) + 1
                    secrets.append(Evidence(file=posix, line=line, snippet=f"looks like a {kind}"))
    yield result(
        None, "warn" if artifacts else "pass",
        f"{len(artifacts)} compiled/system file(s) committed; only sources should be submitted." if artifacts
        else "No object files, binaries or .DS_Store committed.",
        title="Repository contains no build artifacts", evidence=artifacts[:30],
    )
    yield result(
        None, "fail" if secrets else "pass",
        f"{len(secrets)} possible secret(s) found." if secrets else "No credentials or private keys found.",
        title="Repository contains no secrets", evidence=secrets[:30],
    )


def _anywhere(pattern: str) -> str | None:
    """`*/*.c` (or `**/*.c`) names a wildcard whose folder does not matter: the bare `*.c`, else None."""
    *folders, name = pattern.split("/")
    return name if folders and all(f in ("*", "**") for f in folders) and any(c in name for c in "*?[") else None


def _find(ctx: Ctx, unit: str, pattern: str, *, root_only: bool = False) -> list[Path]:
    """What `pattern` names in the unit: files, or a folder when it ends with `/`. `root_only`: a wildcard counts only at the root.
    Outside the strict projects a wildcard counts in any subfolder (`*/*.h` is met by include/x.h or include/sub/x.h)."""
    base = ctx.unit_dir(unit)
    folder = pattern.endswith("/")
    pattern = pattern.rstrip("/") if folder else pattern
    if not ctx.strict_layout and (bare := _anywhere(pattern)):
        pattern = bare
    if "/" in pattern:
        hits = base.glob(pattern)
    elif any(c in pattern for c in "*?["):
        hits = base.glob(pattern) if root_only else base.rglob(pattern)
    else:
        hits = [base / pattern]
    out = []
    for p in hits:
        rel = p.relative_to(ctx.repo.resolve()).as_posix() if p.is_relative_to(ctx.repo.resolve()) else ""
        if rel and not p.is_symlink() and (p.is_dir() if folder else p.is_file()) and not ctx.is_vendored(rel + ("/" if folder else "")):
            out.append(p)
    return out


def _elsewhere(ctx: Ctx, unit: str, pattern: str) -> list[str]:
    """Files (or folders) that have the name or match the wildcard of `pattern` but sit elsewhere in the unit, e.g. includes/libft.h
    for libft.h. Outside the strict projects the whole repository is searched (the layout is free there)."""
    folder = pattern.endswith("/")
    name = pattern.rstrip("/").rsplit("/", 1)[-1]
    if not name or name in ("*", "**"):
        return []
    root = ctx.repo.resolve()
    hits: list[str] = []
    for p in (ctx.unit_dir(unit) if ctx.strict_layout else root).rglob(name):
        if (p.is_dir() if folder else p.is_file()) and not p.is_symlink() and p.is_relative_to(root):
            rel = p.relative_to(root).as_posix()
            if ".git" not in rel.split("/") and not ctx.is_vendored(rel + ("/" if folder else "")):
                hits.append(rel + ("/" if folder else ""))
        if len(hits) >= 3:
            break
    return hits


def _after_make(ctx: Ctx, unit: str):
    """Build the unit, for files that are only there once `make` has run (a Makefile that downloads them, a submodule).
    None when nothing can be built here."""
    if ctx.sandbox is None or not ctx.has_makefile(unit):
        return None
    try:
        return ctx.build(unit)
    except SandboxError:
        return None


@checker("required_files", PHASE_STATIC)
def required_files(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    title = label(rule)
    strict = ctx.strict_layout
    moved = ctx.moved_unit(rule.unit) if not strict else rule.unit
    if not ctx.unit_dir(rule.unit).is_dir():
        yield result(rule, "fail", f"Directory `{rule.unit}/` does not exist in the repository.", title=title)
        return
    moved_text = (f" The subject's `{rule.unit}/` folder does not exist: the project shares its code instead (DRY, which this evaluation "
                  f"accepts outside libft, ft_printf and get_next_line), so its files were looked for in `{moved}/`." if moved != rule.unit else "")
    # `root`: the subject says these belong at the root of the repository (binding only in the strict projects).
    # `soft`: they only appear in an example layout.
    root = set(rule.params.get("root") or []) if strict else set()
    soft = set(rule.params.get("soft") or [])

    def search() -> tuple[list[str], list[str], list[str], int]:
        missing, relocated, expected, found = [], [], [], 0
        for alternatives in rule.params["files"]:
            if any(_find(ctx, rule.unit, alt, root_only=alt in root) for alt in alternatives):
                found += 1
                continue
            wanted = " or ".join(alternatives)
            elsewhere = [hit for alt in alternatives for hit in _elsewhere(ctx, rule.unit, alt)][:3]
            if elsewhere and all(alt in root for alt in alternatives):     # the subject is explicit about the root: elsewhere is not enough
                missing.append(f"{wanted} (it is at {', '.join(f'`{hit}`' for hit in elsewhere)}, but the subject says it belongs at the root)")
            elif elsewhere:                             # there, but not where the list says: a question about structure, not a missing file
                relocated.append(f"{wanted} → {', '.join(f'`{hit}`' for hit in elsewhere)}")
            elif all(alt in soft for alt in alternatives):   # only shown in an example layout of the subject
                expected.append(wanted)
            else:
                hint = ""
                lowered = {p.name.lower() for p in ctx.unit_dir(rule.unit).iterdir()}
                if any(alt.lower() in lowered for alt in alternatives if "*" not in alt):
                    hint = " (a file exists with different letter case)"
                missing.append(wanted + hint)
        return missing, relocated, expected, found

    missing, relocated, expected, found = search()
    after_make = ""
    if missing:
        # "Copy it into your repository" is met by any way of getting it there, as long as the files are there once `make` ran.
        build = _after_make(ctx, rule.unit)
        if build is not None:
            before = len(missing)
            missing, relocated, expected, found = search()
            if len(missing) < before:
                after_make = " Some of them only appear once `make` has run (a submodule or a download in the Makefile), which counts."
            if missing and (reason := ctx.offline_reason(build)):
                yield result(rule, "warn", f"Not in the repository: {', '.join(missing)}. They may come with the build, but {reason}",
                             title=title, log=build.log)
                return
    notes = rule.params.get("notes") or []
    note_text = f" Not machine-checkable: {'; '.join(notes)}." if notes else ""
    if strict:
        elsewhere_text = (f" Found elsewhere than listed: {'; '.join(relocated)}. If the subject lets you organise the project in subfolders "
                          "this is fine; a human (or the AI review) should confirm it does.") if relocated else ""
        expected_text = (f" Not found, but the subject only shows these in an example layout: {', '.join(f'`{e}`' for e in expected)}. "
                         "Whether the layout matters is for a human (or the AI review) to say.") if expected else ""
    else:
        elsewhere_text = (f" Present in another place than the subject shows: {'; '.join(relocated)}. The layout is free in this project "
                          "(only libft, ft_printf and get_next_line must follow it), so this is fine.") if relocated else ""
        expected_text = (f" The subject's example layout also shows {', '.join(f'`{e}`' for e in expected)}; an example is not a requirement.") if expected else ""
    if missing:
        yield result(rule, "fail", f"Missing: {', '.join(missing)}.{elsewhere_text}{expected_text}{moved_text}{note_text}", title=title)
    elif strict and (relocated or expected):
        yield result(rule, "warn", f"Not exactly as the subject lists.{elsewhere_text}{expected_text}{note_text}", title=title)
    else:
        yield result(rule, "pass", f"All {found + len(relocated)} required file pattern(s) are present.{elsewhere_text}{expected_text}"
                                   f"{moved_text}{after_make}{note_text}", title=title)


# --------------------------------------------------------------------------- "copy your libft into a libft folder"


def _libft_copies(ctx: Ctx) -> list[str]:
    """Folders that hold a copy of a libft: libft.h with a Makefile in the same folder or above it, inside the project. Any folder name
    counts outside the strict projects; how it got there does not matter (committed, a submodule, downloaded by the Makefile)."""
    root = ctx.repo.resolve()
    out: list[str] = []
    for header in root.rglob("libft.h"):
        rel = header.relative_to(root)
        if ".git" in rel.parts or ctx.is_vendored(rel) or len(rel.parts) == 1:
            continue
        for folder in [header.parent, *header.parent.parents]:
            if folder == root:
                break
            if (folder / "Makefile").is_file():
                out.append(folder.relative_to(root).as_posix())
                break
    return sorted(set(out))


def _uses_libft(ctx: Ctx) -> list[str]:
    """Where the project says it uses a libft: a Makefile that names it, or a source that includes libft.h."""
    found: list[str] = []
    for rel in ctx.files():
        if ctx.is_vendored(rel):
            continue
        if rel.name == "Makefile" and re.search(r"\blibft\b", ctx.read(rel), re.I):
            found.append(rel.as_posix())
        elif rel.suffix in (".c", ".h") and re.search(r'#\s*include\s*[<"](?:[\w./]*/)?libft\.h[>"]', ctx.read(rel)):
            found.append(rel.as_posix())
        if len(found) >= 3:
            break
    return found


@checker("libft_copy", PHASE_STATIC)
def libft_copy(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    if any(r.kind == "program" and r.params.get("program") == "libft.a" for r in ctx.rules):
        yield result(rule, "na", "This project is the libft itself.")
        return
    users = _uses_libft(ctx)
    copies = _libft_copies(ctx)
    modules = ctx.submodule_paths()

    def how(folder: str) -> str:
        return f"`{folder}/` (a git submodule)" if any(folder == m or folder.startswith(m.rstrip("/") + "/") for m in modules) else f"`{folder}/`"

    if not users and not copies:
        yield result(rule, "na", "The project does not use a libft.")
        return
    after_make = ""
    if not copies:
        build = _after_make(ctx, ".")
        if build is not None:
            copies = _libft_copies(ctx)
            after_make = " It is only there once `make` has run (downloaded by the Makefile), which counts." if copies else ""
            if not copies and (reason := ctx.offline_reason(build)):
                yield result(rule, "warn", f"The project uses a libft ({', '.join(users)}) that is not in the repository yet. {reason}", log=build.log)
                return
    if copies:
        found = f"The libft sources and Makefile are in the repository: {', '.join(how(c) for c in copies[:3])}.{after_make}"
        evidence = [Evidence(file=f"{c}/Makefile") for c in copies[:3]]
        if any(Path(c).name == "libft" for c in copies):
            yield result(rule, "pass", found, evidence=evidence)
        elif ctx.strict_layout:                         # ft_printf: the format is binding, and the subject says "a libft folder"
            yield result(rule, "warn", f"{found} The subject asks for a folder called libft, and in this project the format is binding.",
                         evidence=evidence)
        else:
            yield result(rule, "pass", f"{found} The folder is not called libft, which is fine: the layout is free outside libft, "
                                       "ft_printf and get_next_line.", evidence=evidence)
    else:
        yield result(rule, "fail", f"The project uses a libft ({', '.join(users)}), but its sources and Makefile are not in the repository "
                                   "(committed, as a submodule, or downloaded by `make`).",
                     evidence=[Evidence(file=u) for u in users])


# --------------------------------------------------------------------------- files added for the evaluation

EXTRA_DIRS = re.compile(r"^(tests?|testers?|unit_?tests?|test_?suite|testing|checker_?tests?|scripts?|tools)$", re.I)
EXTRA_SUFFIXES = {".sh", ".bash", ".zsh", ".py", ".rb", ".pl", ".js", ".ts"}
DOCKER_NAME = re.compile(r"(dockerfile(\.[\w-]+)?|[\w.-]+\.dockerfile|(docker-)?compose(\.[\w-]+)?\.ya?ml)", re.I)


def evaluation_extras(ctx: Ctx) -> list[str]:
    """Files that the subject does not ask for and that serve to evaluate or run the project: test suites, scripts, Docker files."""
    found: dict[str, None] = {}
    for rel in ctx.files():
        if ctx.is_vendored(rel) or rel.name.startswith(".") and rel.suffix not in EXTRA_SUFFIXES:
            continue
        folder = next((part for part in rel.parts[:-1] if EXTRA_DIRS.match(part)), None)
        if folder:
            found.setdefault("/".join(rel.parts[: rel.parts.index(folder) + 1]) + "/")
        elif rel.suffix.lower() in EXTRA_SUFFIXES or DOCKER_NAME.fullmatch(rel.name):
            found.setdefault(rel.as_posix())
        if len(found) >= 12:
            break
    return list(found)


def extras_check(ctx: Ctx) -> Iterable[CheckResult]:
    extras = evaluation_extras(ctx)
    if extras:
        yield result(None, "manual",
                     f"The repository has files added for the evaluation: {', '.join(f'`{e}`' for e in extras)}. That is allowed, but they "
                     "must work: run them (the test suite, the scripts, `docker build` / `docker compose up --build`). If one is broken, the "
                     "project fails because of it.",
                     title="Files added for the evaluation work", evidence=[Evidence(file=e.rstrip("/")) for e in extras], auto=False)


def _has_target(makefile: str, target: str) -> bool:
    if target == "NAME":
        return bool(re.search(r"^\s*NAME\s*[:+?]?=", makefile, re.M) or re.search(r"^\$\(NAME\)\s*:", makefile, re.M))
    return bool(re.search(rf"^(?:[\w.$()/-]+[ \t]+)*{re.escape(target)}(?:[ \t]+[\w.$()/-]+)*[ \t]*:(?!=)", makefile, re.M))


@checker("makefile_rules", PHASE_STATIC)
def makefile_rules(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    title = label(rule)
    path = ctx.unit_dir(rule.unit) / "Makefile"
    if not path.is_file():
        yield result(rule, "fail", f"No Makefile in `{rule.unit}/`.", title=title)
        return
    makefile = path.read_text(errors="replace")
    targets = list(dict.fromkeys(rule.params["targets"]))
    missing = [t for t in targets if not _has_target(makefile, t)]
    if missing:
        yield result(rule, "fail", f"Makefile is missing: {', '.join(missing)}.", title=title)
    else:
        yield result(rule, "pass", f"Makefile defines {', '.join(targets)}.", title=title)


@checker("language", PHASE_STATIC)
def language(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    wrong_cpp = [p for p in ctx.files() if p.suffix.lower() in (".cpp", ".cc", ".hpp", ".cxx") and not ctx.is_vendored(p)]
    other = [p for p in ctx.files() if p.suffix.lower() in (".py", ".rs", ".go", ".java", ".js", ".ts", ".rb", ".php", ".cs")
             and not ctx.is_vendored(p)]
    if wrong_cpp:
        yield result(rule, "fail", "C++ files found in a C project.",
                     evidence=[Evidence(file=p.as_posix()) for p in wrong_cpp[:20]])
    elif not any(p.suffix == ".c" for p in ctx.files()):
        yield result(rule, "fail", "No .c files found.")
    elif other:
        # Test scripts and tools added for the evaluation are allowed (they must work: see "Files added for the evaluation work").
        yield result(rule, "pass", f"The project is written in C. The {len(other)} file(s) in other languages are extras such as test scripts, "
                                   "which are allowed as long as they work.",
                     evidence=[Evidence(file=p.as_posix()) for p in other[:20]])
    else:
        yield result(rule, "pass", "Only C sources found.")


@checker("include_guards", PHASE_STATIC)
def include_guards(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    headers = [p for p in ctx.source_files() if p.suffix.lower() in (".h", ".hpp")]
    bad = []
    for rel in headers:
        text = ctx.read(rel)
        guarded = re.search(r"#\s*pragma\s+once", text) or re.search(r"#\s*ifndef\s+(\w+)\s*\n\s*#\s*define\s+\1\b", text)
        if not guarded:
            bad.append(Evidence(file=rel.as_posix(), snippet="no include guard"))
    if not headers:
        yield result(rule, "skipped", "No header files found.")
    elif bad:
        yield result(rule, "fail", f"{len(bad)} of {len(headers)} header(s) have no include guard.", evidence=bad)
    else:
        yield result(rule, "pass", f"All {len(headers)} header(s) have include guards.")


@checker("cpp_forbidden_calls", PHASE_STATIC)
def cpp_forbidden_calls(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    pattern = re.compile(r"(?<![\w.>])(?:[vfsdn]*printf|malloc|calloc|realloc|free)\s*\(")
    hits = grep(ctx, ctx.source_files(), pattern)
    if hits:
        yield result(rule, "fail", "Forbidden call(s) found (grade 0 per the subject).", evidence=hits)
    else:
        yield result(rule, "pass", "No *printf(), *alloc() or free() calls found.")


@checker("cpp_forbidden_keywords", PHASE_STATIC)
def cpp_forbidden_keywords(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    hits = grep(ctx, ctx.source_files(), re.compile(r"\busing\s+namespace\b|\bfriend\b"))
    if hits:
        yield result(rule, "fail", "`using namespace` / `friend` used (forbidden unless the exercise says otherwise).", evidence=hits)
    else:
        yield result(rule, "pass", "Neither `using namespace` nor `friend` appears.")


@checker("cpp_no_stl", PHASE_STATIC)
def cpp_no_stl(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    module = rule.params.get("module")
    if module is None or module >= 8:
        yield result(rule, "skipped", "The STL is allowed in this module.")
        return
    pattern = re.compile(
        r"#\s*include\s*<(vector|list|map|multimap|set|multiset|stack|queue|deque|algorithm|iterator|"
        r"unordered_map|unordered_set|array|bitset|functional|numeric)>"
    )
    hits = grep(ctx, ctx.source_files(), pattern, code_only=False)
    if hits:
        yield result(rule, "fail", "STL containers/algorithms are forbidden before module 08 (grade -42).", evidence=hits)
    else:
        yield result(rule, "pass", "No STL container or algorithm headers included.")


@checker("bonus_rule", PHASE_STATIC)
def bonus_rule(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    bonus_files = [p for p in ctx.files() if re.search(r"bonus", p.name, re.I) and p.suffix in (".c", ".h", ".cpp", ".hpp")]
    if not bonus_files:
        yield result(rule, "na", "No bonus files in the repository, so no bonus rule is required.")
        return
    path = ctx.unit_dir(rule.unit) / "Makefile"
    text = path.read_text(errors="replace") if path.is_file() else ""
    if _has_target(text, "bonus"):
        yield result(rule, "pass", "Bonus files found and the Makefile has a `bonus` rule.")
    else:
        yield result(rule, "fail", "Bonus files found but the Makefile has no `bonus` rule.",
                     evidence=[Evidence(file=p.as_posix()) for p in bonus_files[:10]])


@checker("manual", PHASE_STATIC)
def manual(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    yield result(rule, "manual", rule.text, auto=False)


@checker("readme", PHASE_STATIC)
def readme(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    root_files = [p for p in ctx.files() if len(p.parts) == 1]
    exact = next((p for p in root_files if p.name == "README.md"), None)
    if exact is None:
        other = next((p for p in root_files if p.name.lower().startswith("readme")), None)
        if other:
            yield result(rule, "fail", f"Found `{other.name}`, but the subject requires a file named exactly README.md at the root.")
        else:
            yield result(rule, "fail", "No README.md found at the root of the repository. The subject requires one.")
        return
    text = ctx.read(exact)
    lines = text.splitlines()
    first = next((l.strip() for l in lines if l.strip()), "")
    problems: list[str] = []
    if not re.fullmatch(r"([*_])\s*This project has been created as part of the 42 curriculum by .+?\s*\1", first, re.I):
        problems.append("the very first line must be italicized and read: *This project has been created as part of the 42 curriculum by <login>*")
    elif re.search(r"<\s*login", first, re.I):
        problems.append("the first line still contains the <login> placeholder")
    headings = [(i, re.sub(r"[:#*_`\s]+", " ", l).strip().lower()) for i, l in enumerate(lines)
                if re.match(r"\s{0,3}#{1,6}\s+\S", l)]
    for section in rule.params["sections"]:
        if not any(section.lower() in h for _, h in headings):
            problems.append(f"missing a “{section}” section")
    evidence = [Evidence(file="README.md", line=1, snippet=first[:160])]
    if problems:
        yield result(rule, "fail", "README.md: " + "; ".join(problems) + ".", evidence=evidence)
        return
    resources = next((i for i, h in headings if "resources" in h), None)
    if resources is not None:
        end = next((i for i, _ in headings if i > resources), len(lines))
        if not re.search(r"\bAI\b|artificial intelligence|chatgpt|claude|copilot|gemini|\bLLM\b", "\n".join(lines[resources:end]), re.I):
            yield result(rule, "warn", "README.md is complete, but its Resources section does not say how AI was used (the subject asks for it, even if the answer is “not used”).",
                         evidence=[Evidence(file="README.md", line=resources + 1)])
            return
    yield result(rule, "pass", f"README.md has the required first line and sections ({len(lines)} lines).")
