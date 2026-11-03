"""Checks that only read files; they never need the sandbox."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from ..models import CheckResult, Evidence, Rule
from . import (
    EXCLUDED_DIRS, PHASE_STATIC, Ctx, checker, grep, label, result,
)

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
        if EXCLUDED_DIRS.search("/" + posix):
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


def _find(ctx: Ctx, unit: str, pattern: str) -> list[Path]:
    base = ctx.unit_dir(unit)
    if "/" in pattern:
        hits = base.glob(pattern)
    elif any(c in pattern for c in "*?["):
        hits = base.rglob(pattern)
    else:
        hits = [base / pattern]
    out = []
    for p in hits:
        rel = p.relative_to(ctx.repo.resolve()).as_posix() if p.is_relative_to(ctx.repo.resolve()) else ""
        if rel and p.is_file() and not p.is_symlink() and not EXCLUDED_DIRS.search("/" + rel):
            out.append(p)
    return out


def _elsewhere(ctx: Ctx, unit: str, pattern: str) -> list[str]:
    """Files that have the name (or match the wildcard) of `pattern` but sit elsewhere in the unit, e.g. includes/libft.h for libft.h.
    The subject may well allow that, so the check does not decide: it points at them."""
    name = pattern.rsplit("/", 1)[-1]
    if not name or name in ("*", "**"):
        return []
    root = ctx.repo.resolve()
    hits: list[str] = []
    for p in ctx.unit_dir(unit).rglob(name):
        if p.is_file() and not p.is_symlink() and p.is_relative_to(root):
            rel = p.relative_to(root).as_posix()
            if not EXCLUDED_DIRS.search("/" + rel):
                hits.append(rel)
        if len(hits) >= 3:
            break
    return hits


@checker("required_files", PHASE_STATIC)
def required_files(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    title = label(rule)
    if not ctx.unit_dir(rule.unit).is_dir():
        yield result(rule, "fail", f"Directory `{rule.unit}/` does not exist in the repository.", title=title)
        return
    missing, relocated, found = [], [], 0
    for alternatives in rule.params["files"]:
        if any(_find(ctx, rule.unit, alt) for alt in alternatives):
            found += 1
            continue
        wanted = " or ".join(alternatives)
        elsewhere = [hit for alt in alternatives for hit in _elsewhere(ctx, rule.unit, alt)][:3]
        if elsewhere:                                   # there, but not where the list says: a question about structure, not a missing file
            relocated.append(f"{wanted} → {', '.join(f'`{hit}`' for hit in elsewhere)}")
            continue
        hint = ""
        lowered = {p.name.lower() for p in ctx.unit_dir(rule.unit).iterdir()}
        if any(alt.lower() in lowered for alt in alternatives if "*" not in alt):
            hint = " (a file exists with different letter case)"
        missing.append(wanted + hint)
    notes = rule.params.get("notes") or []
    note_text = f" Not machine-checkable: {'; '.join(notes)}." if notes else ""
    elsewhere_text = (f" Found elsewhere than listed: {'; '.join(relocated)}. If the subject lets you organise the project in subfolders "
                      "this is fine; a human (or the AI review) should confirm it does.") if relocated else ""
    if missing:
        yield result(rule, "fail", f"Missing: {', '.join(missing)}.{elsewhere_text}{note_text}", title=title)
    elif relocated:
        yield result(rule, "warn", f"Not at the place the list gives.{elsewhere_text}{note_text}", title=title)
    else:
        yield result(rule, "pass", f"All {found} required file pattern(s) are present.{note_text}", title=title)


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
    wrong_cpp = [p for p in ctx.files() if p.suffix.lower() in (".cpp", ".cc", ".hpp", ".cxx") and not EXCLUDED_DIRS.search("/" + p.as_posix())]
    other = [p for p in ctx.files() if p.suffix.lower() in (".py", ".rs", ".go", ".java", ".js", ".ts", ".rb", ".php", ".cs")
             and not EXCLUDED_DIRS.search("/" + p.as_posix())]
    if wrong_cpp:
        yield result(rule, "fail", "C++ files found in a C project.",
                     evidence=[Evidence(file=p.as_posix()) for p in wrong_cpp[:20]])
    elif other:
        yield result(rule, "warn", "Files in other languages are present; make sure the project itself is C.",
                     evidence=[Evidence(file=p.as_posix()) for p in other[:20]])
    elif not any(p.suffix == ".c" for p in ctx.files()):
        yield result(rule, "fail", "No .c files found.")
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
