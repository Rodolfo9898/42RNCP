"""Turn the text of a 42 subject into a list of checkable rules.

42 subjects share a layout: a table of fields (`Program Name`, `Files to Submit`,
`Makefile`, `External Function`, ...) for each deliverable, plus shared "general
rules" prose. The table is parsed structurally; the prose is matched against a
list of known rules, and any other requirement-looking sentence becomes a manual
rule so that nothing in the subject is silently dropped.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .models import Rule, Section, Source

LABELS = {
    "program name": "program",
    "files to submit": "files",
    "turn in files": "files",
    "turn-in files": "files",
    "makefile": "makefile",
    "arguments": "arguments",
    "external function": "functions",
    "external functions": "functions",
    "external functs.": "functions",
    "libft authorized": "libft",
    "description": "description",
    "function name": "function_name",
    "prototype": "prototype",
    "parameters": "parameters",
    "return value": "return_value",
}

# Chapters whose prose never contains requirements for the repository.
SKIPPED_CHAPTERS = (
    "introduction", "foreword", "preamble", "ai instructions", "objectives",
    "submission and peer", "contents", "table of contents",
)

REQUIREMENT_WORDS = re.compile(
    r"\b(must|should|forbidden|not allowed|prohibited|mandatory|required|cannot|can't|"
    r"should not|shouldn't|grade will be|will (?:receive|be considered)|strictly)\b",
    re.I,
)

DEFAULT_MAKEFILE_RULES = ["NAME", "all", "clean", "fclean", "re"]

# Functions that only appear through well-known libraries named in "External Function".
MATH_FUNCTIONS = [
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sqrt", "pow", "exp", "log",
    "log2", "log10", "fabs", "floor", "ceil", "round", "fmod", "hypot", "cbrt", "trunc",
]


@dataclass
class Line:
    text: str
    page: int
    section: Section
    chapter: str


@dataclass
class Spec:
    name: str
    lang: str | None = None  # "c" | "cpp" | None
    rules: list[Rule] = field(default_factory=list)


def label_of(text: str) -> str | None:
    return LABELS.get(text.strip().rstrip(":").strip().lower())


def _is_toc_page(lines: list[str], previous_was_toc: bool) -> bool:
    if not lines:
        return False
    if lines[0].lower() in ("contents", "table of contents"):
        return True
    if not previous_was_toc:
        return False
    numeric = sum(1 for l in lines if re.fullmatch(r"\d+|[ivxlc]+", l, re.I))
    return numeric / len(lines) > 0.3


def read_lines(pages: list[str]) -> list[Line]:
    """Flatten pages into lines, dropping TOC pages, page numbers and running headers."""
    split = [[l.strip() for l in p.splitlines() if l.strip()] for p in pages]
    counts = Counter(l for page in split for l in set(page))
    repeated = max(3, int(len(pages) * 0.4))

    out: list[Line] = []
    section: Section = "mandatory"
    chapter = ""
    expect_title = False
    toc = False
    for number, page in enumerate(split, 1):
        toc = _is_toc_page(page, toc)
        if toc:
            continue
        for text in page:
            if re.fullmatch(r"\d+", text) or (counts[text] >= repeated and label_of(text) is None):
                continue
            if re.fullmatch(r"chapter [ivxlc]+", text, re.I):
                expect_title = True
                continue
            heading = text if expect_title else None
            if expect_title:
                chapter = text.lower()
                expect_title = False
            m = re.fullmatch(r"(mandatory|bonus) part", text, re.I)
            if m:
                section = "bonus" if m.group(1).lower() == "bonus" else "mandatory"
                chapter = text.lower()
                continue
            if heading is not None:
                continue  # chapter titles are structure, not content
            out.append(Line(text, number, section, chapter))
    return out


def _rule(kind: str, title: str, *, text: str = "", section: Section = "mandatory",
          unit: str = ".", params: dict[str, Any] | None = None,
          source: Source | None = None) -> Rule:
    params = params or {}
    digest = hashlib.sha1(json.dumps([kind, unit, section, params], sort_keys=True).encode()).hexdigest()[:8]
    return Rule(
        id=f"{kind}:{digest}", kind=kind, title=title, text=text, section=section,
        unit=unit, params=params, sources=[source] if source else [],
    )


# --------------------------------------------------------------------------- tables


def _root_or_subfolder(required: list[list[str]]) -> list[list[str]]:
    """`*.c` and `*/*.c` in one list mean "at the root or in a subfolder": either place satisfies it, so they are one requirement
    (a project that keeps everything at the root must not be told that its `*/*.c` is missing)."""
    known = {tuple(entry) for entry in required}
    merged: list[list[str]] = []
    for entry in required:
        if all(a.startswith("*/") for a in entry) and tuple(a[2:] for a in entry) in known:
            continue                                            # folded into the entry for the root
        twin = tuple("*/" + a for a in entry)
        merged.append(entry + list(twin) if twin in known else entry)
    return merged


def expand_files(value: str) -> tuple[list[list[str]], list[str]]:
    """Parse a 'Files to Submit' value.

    Returns (required, notes). Each entry of `required` is a list of alternatives, any
    one of which satisfies it (`*.{h, hpp}` means `*.h` or `*.hpp`; `*.c` with `*/*.c` means
    the root or a subfolder). `notes` holds prose fragments that could not be turned into a file pattern.
    """
    value = re.sub(r"\{([^}]*)\}", lambda m: "{" + re.sub(r"[,\s]+", "|", m.group(1).strip()) + "}", value)
    required: list[list[str]] = []
    notes: list[str] = []
    for chunk in re.split(r",", value):
        for token in chunk.split("+"):
            token = token.strip().strip(".")
            if not token or token in ("-", "n/a"):
                continue
            if not re.fullmatch(r"[\w./*{}|-]+", token) or not ("." in token or "*" in token or token == "Makefile"):
                if token.lower() != "makefile":
                    notes.append(token)
                    continue
            m = re.fullmatch(r"(.*)\{([^}]*)\}(.*)", token)
            alternatives = [m.group(1) + a + m.group(3) for a in m.group(2).split("|")] if m else [token]
            required.append(alternatives)
    return _root_or_subfolder(required), notes


# Words that show up in 'External Function' prose but are not function names.
NOT_FUNCTIONS = {
    "or", "any", "equivalent", "coded", "all", "functions", "function", "of", "the", "library",
    "math", "minilibx", "lm", "compiler", "option", "man", "and", "in", "c", "implemented",
    "functionality", "must", "be", "detailed", "below", "none", "n", "a", "your", "own",
}


def _identifiers(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for name in re.findall(r"\b[a-z_][a-z0-9_]*\b", text):
        if name not in NOT_FUNCTIONS:
            seen.setdefault(name)
    return list(seen)


def _program_rules(fields: dict[str, str], section: Section, source: Source) -> list[Rule]:
    files = fields.get("files", "")
    unit = "."
    m = re.search(r"in (?:the )?director(?:y|ies)\s+([\w./-]+)", files, re.I)
    if m:
        unit = m.group(1).rstrip("/.,") or "."
        files = files[: m.start()]
    program = fields.get("program", "").strip()
    rules: list[Rule] = []

    required, notes = expand_files(files)
    if required:
        rules.append(_rule("required_files", "Required files", text=f"Files to submit: {fields.get('files', '')}",
                           section=section, unit=unit, params={"files": required, "notes": notes}, source=source))
    elif notes:
        rules.append(_rule("manual", "Files to submit", text=f"Files to submit: {fields.get('files', '')}",
                           section=section, unit=unit, params={"text": files}, source=source))

    mk = fields.get("makefile", "")
    targets = [t for t in re.findall(r"[\w$()]+", mk) if t]
    if targets:
        targets = ["NAME" if t in ("$(NAME)", "NAME") else t for t in targets]
        rules.append(_rule("makefile_rules", "Makefile rules", text=f"Makefile: {mk}", section=section,
                           unit=unit, params={"targets": targets}, source=source))

    if program:
        rules.append(_rule("program", f"Builds `{program}`", text=f"Program name: {program}", section=section,
                           unit=unit, params={"program": program, "bonus_target": section == "bonus"}, source=source))

    fn_text = fields.get("functions", "")
    libft = fields.get("libft", "").strip().lower()
    if fn_text and not re.search(r"detailed below", fn_text, re.I):
        names = _identifiers(re.sub(r"\([^)]*\)", lambda m: " " + m.group(0)[1:-1] + " ", fn_text))
        names = [n for n in names if n not in ("c",)]
        params: dict[str, Any] = {
            "functions": names,
            "libft": libft.startswith("yes"),
            "math": bool(re.search(r"math library", fn_text, re.I)),
            "mlx": bool(re.search(r"minilibx", fn_text, re.I)),
            "own_allowed": bool(re.search(r"equivalent|YOU coded", fn_text, re.I)),
        }
        rules.append(_rule("allowed_functions", "Only authorized external functions", text=f"External functions: {fn_text}",
                           section=section, unit=unit, params=params, source=source))
    elif libft.startswith("no"):
        pass
    return rules


def _cpp_exercise_rules(lines: list[Line], source_pdf: str) -> list[Rule]:
    """C++ modules list each exercise as `Directory: exNN/` + `Files to Submit: ...`."""
    rules: list[Rule] = []
    i = 0
    while i < len(lines):
        m = re.match(r"Directory:\s*(\S+)", lines[i].text)
        if not m:
            i += 1
            continue
        unit = m.group(1).rstrip("/") or "."
        section, source = lines[i].section, Source(pdf=source_pdf, page=lines[i].page)
        files = ""
        j = i + 1
        while j < len(lines) and lines[j].text.lower().startswith("files to submit:"):
            files = lines[j].text.split(":", 1)[1].strip()
            while files.endswith(",") and j + 1 < len(lines):
                j += 1
                files += " " + lines[j].text
            j += 1
        required, notes = expand_files(files)
        if required:
            rules.append(_rule("required_files", "Required files", text=f"Files to submit: {files}",
                               section=section, unit=unit, params={"files": required, "notes": notes}, source=source))
        rules.append(_rule("build_unit", f"{unit}: compiles", text=f"Exercise {unit}", section=section,
                           unit=unit, params={}, source=source))
        rules.append(_rule("makefile_rules", "Makefile rules", text="Makefile rules (same rules as C)", section=section,
                           unit=unit, params={"targets": DEFAULT_MAKEFILE_RULES}, source=source))
        i = j
    return rules


def _parse_tables(lines: list[Line], pdf: str) -> list[Rule]:
    rules: list[Rule] = []
    names: dict[Section, list[str]] = {"mandatory": [], "bonus": []}
    allowed: dict[Section, dict[str, Any]] = {}
    is_libft = False
    i = 0
    while i < len(lines):
        first = label_of(lines[i].text)
        if first not in ("program", "function_name"):
            i += 1
            continue
        start = lines[i]
        fields: dict[str, list[str]] = {}
        current = None
        j = i
        while j < len(lines):
            label = label_of(lines[j].text)
            if label:
                current = label
                if label == "description":
                    j += 1
                    break
                fields.setdefault(label, [])
            elif current:
                fields[current].append(lines[j].text)
            else:
                break
            j += 1
        flat = {k: " ".join(v).strip() for k, v in fields.items()}
        source = Source(pdf=pdf, page=start.page)
        if first == "program":
            rules.extend(_program_rules(flat, start.section, source))
            is_libft = is_libft or flat.get("program", "").strip() == "libft.a"
        else:
            # Function-style subjects (get_next_line, libft): one entry per function.
            if flat.get("function_name"):
                names[start.section].append(flat["function_name"].strip())
            required, notes = expand_files(flat.get("files", ""))
            if required or notes:
                rules.append(_rule("required_files", "Required files", text=f"Files to submit: {flat.get('files', '')}",
                                   section=start.section, params={"files": required, "notes": notes}, source=source))
            acc = allowed.setdefault(start.section, {"functions": [], "source": source})
            for name in _identifiers(flat.get("functions", "")):
                if name not in acc["functions"]:
                    acc["functions"].append(name)
        i = max(j, i + 1)

    for section, acc in allowed.items():
        if acc["functions"]:
            rules.append(_rule("allowed_functions", "Only authorized external functions",
                               text=f"External functions: {', '.join(acc['functions'])}", section=section,
                               params={"functions": acc["functions"], "libft": False, "math": False, "mlx": False,
                                       "own_allowed": False}, source=acc["source"]))

    if is_libft:
        names["mandatory"] = _libft_part1(lines) + names["mandatory"]
    for section in ("mandatory", "bonus"):
        if names[section]:
            rules.append(_rule("functions_defined", "Required functions are defined",
                               text=f"{len(names[section])} functions: {', '.join(names[section])}",
                               section=section, params={"names": names[section]}, source=Source(pdf=pdf, page=1)))
    return rules


def _libft_part1(lines: list[Line]) -> list[str]:
    names: list[str] = []
    inside = False
    for line in lines:
        if re.match(r"part 1\b", line.text, re.I):
            inside = True
        elif re.match(r"part 2\b", line.text, re.I):
            break
        elif inside:
            m = re.fullmatch(r"[•◦]\s*([a-z_0-9]+)", line.text)
            if m:
                names.append("ft_" + m.group(1))
    return names


# --------------------------------------------------------------------------- prose


def _prose_items(lines: list[Line]) -> list[tuple[str, Line]]:
    """Group wrapped lines into bullet items / paragraphs."""
    items: list[tuple[str, Line]] = []
    buf = ""
    head: Line | None = None
    for line in lines:
        starts = line.text[:1] in "•◦" or (buf and re.search(r"[.!?:]$", buf))
        if buf and starts:
            items.append((buf, head))  # type: ignore[arg-type]
            buf, head = "", None
        if not buf:
            head = line
        buf = (buf + " " + line.text).strip()
    if buf and head:
        items.append((buf, head))
    out: list[tuple[str, Line]] = []
    for text, line in items:
        text = re.sub(r"(\w)- (\w)", r"\1\2", text)  # un-hyphenate wrapped words
        text = re.sub(r"^[•◦]\s*", "", text)
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z•])", text):
            if 25 <= len(sentence) <= 500:
                out.append((sentence.strip(), line))
    return out


def _cpp_module(pdf: str, text: str) -> int | None:
    m = re.search(r"cpp(\d\d)", pdf, re.I) or re.search(r"Module\s+(\d\d)", text)
    return int(m.group(1)) if m else None


def _classify(sentence: str, line: Line, pdf: str, module: int | None) -> Rule | None:
    s = sentence
    section, source = line.section, Source(pdf=pdf, page=line.page)
    low = s.lower()

    def mk(kind: str, title: str, **params: Any) -> Rule:
        return _rule(kind, title, text=s, section=section, params=params, source=source)

    if re.search(r"-Wall.*-Wextra.*-Werror", s):
        compiler = "c++" if re.search(r"\bc\+\+\b", low) and "cc" not in re.findall(r"\bcc\b", low) else "cc"
        return mk("flags", "Compiles with -Wall -Wextra -Werror", flags=["-Wall", "-Wextra", "-Werror"], compiler=compiler)
    if "-std=c++98" in s:
        return mk("std98", "Still compiles with -std=c++98")
    if re.search(r"accordance with the norm|follow the norm", low) and "goodbye" not in low:
        return mk("norm", "Passes norminette")
    if "unnecessary relinking" in low:
        return mk("no_relink", "Makefile does not relink")
    if re.search(r"makefile must contain at least the rules", low):
        return mk("makefile_rules", "Makefile rules", targets=DEFAULT_MAKEFILE_RULES)
    if re.search(r"quit unexpectedly|segmentation fault", low):
        return mk("no_crash", "Does not crash")
    if re.search(r"must be written in c\b", low):
        return mk("language", "Written in C", lang="c")
    if re.search(r"memory leak|properly freed", low):
        return mk("no_leaks", "No memory leaks")
    if re.search(r"global variables?", low) and re.search(r"forbidden|not allowed", low) and "one global" not in low:
        return mk("no_globals", "No global variables")
    if "bonus rule" in low and "makefile" in low:
        return mk("bonus_rule", "Makefile has a bonus rule")
    if re.search(r"\*printf\(\).*\*alloc\(\).*free\(\)", s) or re.search(r"printf.*alloc.*free.*forbidden", low):
        return mk("cpp_forbidden_calls", "No *printf(), *alloc() or free()", names=["printf", "alloc", "free"])
    if "using namespace" in low and "friend" in low and "forbidden" in low:
        return mk("cpp_forbidden_keywords", "No `using namespace` or `friend`")
    if re.search(r"stl only in modules?", low):
        return mk("cpp_no_stl", "No STL containers/algorithms before module 08", module=module)
    if re.search(r"readme\.md.*must be provided|readme\.md must include|first line must be italicized", low):
        return mk("readme", "README.md meets the subject's requirements",
                  sections=["Description", "Instructions", "Resources"])
    if "include guards" in low:
        return mk("include_guards", "Headers have include guards")
    return None


def _prose_rules(lines: list[Line], pdf: str, module: int | None) -> list[Rule]:
    prose = [l for l in lines if not any(c in l.chapter for c in SKIPPED_CHAPTERS)]
    rules: list[Rule] = []
    for sentence, line in _prose_items(prose):
        rule = _classify(sentence, line, pdf, module)
        if rule is None and REQUIREMENT_WORDS.search(sentence):
            rule = _rule("manual", "Needs manual review", text=sentence, section=line.section,
                         params={"text": sentence}, source=Source(pdf=pdf, page=line.page))
        if rule:
            rules.append(rule)
    return rules


# --------------------------------------------------------------------------- entry points


def parse_subject(pdf: str, pages: list[str]) -> Spec:
    lines = read_lines(pages)
    full = "\n".join(l.text for l in lines)
    module = _cpp_module(pdf, full)

    rules = _parse_tables(lines, pdf) + _cpp_exercise_rules(lines, pdf)
    rules += _prose_rules(lines, pdf, module)

    lang = None
    if any(r.kind == "std98" for r in rules):
        lang = "cpp"
    elif re.search(r"must be written in C\b", full):
        lang = "c"
    return Spec(name=pdf, lang=lang, rules=merge_rules(rules))


def parse_norm(pdf: str, pages: list[str]) -> Spec:
    """The Norm (en.norm.pdf): norminette checks most of it; the rules it marks with (*) need a human."""
    lines = read_lines(pages)
    first = next((l for l in lines if "norminette" in l.text.lower()), lines[0] if lines else None)
    rules = [_rule("norm", "Passes norminette", text="The code must follow the Norm (checked by norminette).",
                   source=Source(pdf=pdf, page=first.page) if first else None)]
    for sentence, line in _prose_items(lines):
        m = re.match(r"(?:[-•◦]\s*)?\(\*\)\s*(.+)", sentence)
        if m:
            text = m.group(1)
            rules.append(_rule("manual", "Norm rule norminette cannot check", text=text, params={"text": text},
                               source=Source(pdf=pdf, page=line.page)))
    return Spec(name=pdf, lang="c", rules=merge_rules(rules))


def merge_rules(rules: list[Rule]) -> list[Rule]:
    """Collapse identical rules (same id), remembering every place they came from."""
    merged: dict[str, Rule] = {}
    for rule in rules:
        existing = merged.get(rule.id)
        if existing is None:
            merged[rule.id] = rule.model_copy(deep=True)
        else:
            for src in rule.sources:
                if src not in existing.sources:
                    existing.sources.append(src)
    return list(merged.values())
