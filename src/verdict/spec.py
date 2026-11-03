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
                if re.search(r"deliverable|submission|turn-?in", chapter):
                    section = "mandatory"           # what to hand in concerns the whole project, not the bonus part that came before
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


def _file_params(required: list[list[str]], notes: list[str]) -> dict[str, Any]:
    """The parameters of a required_files rule. A note such as "all at the root of the repository" is a requirement too: the files
    it covers must be at the root, not merely somewhere in the project."""
    params: dict[str, Any] = {"files": required, "notes": notes}
    if any(re.search(r"\bat the root\b", note, re.I) for note in notes):
        params["root"] = [alt for entry in required for alt in entry]
    return params


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
                           section=section, unit=unit, params=_file_params(required, notes), source=source))
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
                               section=section, unit=unit, params=_file_params(required, notes), source=source))
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
                                   section=start.section, params=_file_params(required, notes), source=source))
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


def _line_of(lines: list[Line], head: Line, needle: str) -> Line:
    """The line a sentence really sits on: wrapped paragraphs are credited to their first line, which can be pages earlier."""
    start = next((i for i, l in enumerate(lines) if l is head), 0)
    return next((l for l in lines[start:start + 80] if needle.lower() in l.text.lower()), head)


def _prose_rules(lines: list[Line], pdf: str, module: int | None, file_hits: list | None = None) -> list[Rule]:
    prose = [l for l in lines if not any(c in l.chapter for c in SKIPPED_CHAPTERS)]
    rules: list[Rule] = []
    if file_hits is not None:
        # The chapter about turning in the work is skipped for vague requirements, but it is where some subjects say what to turn in.
        turn_in = [l for l in lines if re.search(r"submission|turn-?in", l.chapter)]
        for sentence, line in _prose_items(turn_in):
            names, root = _sentence_files(sentence)
            if names:
                file_hits.append((names, root, _line_of(turn_in, line, names[0])))
    for sentence, line in _prose_items(prose):
        rule = _classify(sentence, line, pdf, module)
        if rule is None and file_hits is not None:
            names, root = _sentence_files(sentence)
            if names:                                   # "You must submit a Makefile": a required file, not a vague manual item
                file_hits.append((names, root, _line_of(prose, line, names[0])))
                continue
        if rule is None and REQUIREMENT_WORDS.search(sentence):
            rule = _rule("manual", "Needs manual review", text=sentence, section=line.section,
                         params={"text": sentence}, source=Source(pdf=pdf, page=line.page))
        if rule:
            rules.append(rule)
    return rules


# --------------------------------------------------------------------------- files the subject names outside its tables
#
# Most subjects give their files in a table ("Files to Submit"), but many only say it in the text: "You must submit a Makefile",
# "a signature.txt file at the root of your repository", a bullet list under "Required Files", or a listing of the expected
# layout. Those become required files too, under strict conditions: an obligation (must, have to, required, ...) that names a
# concrete file, never a condition ("if you use ..."), an example, something optional, something forbidden or a bonus.

FILE_NAME = r"(?:[\w.\-]+/)*[A-Za-z0-9_][\w.\-]*\.[A-Za-z][A-Za-z0-9]{0,5}"
BARE_NAMES = {"Makefile", "Dockerfile"}
_HANDED_IN = r"(?:submit|turn[- ]?in|hand in|provide|deposit|ship|deliver)"
_ARTICLE = r"(?:an?|the|your|its)"
_OBLIGED = re.compile(r"\b(must|have to|has to|need to|needs to|required|mandatory|expected to|should)\b", re.I)
_NOT_AN_OBLIGATION = re.compile(
    r"\b(if|unless|optional|optionally|example|e\.g\.|for instance|such as|similar|do not|don't|must not|should not|shouldn't|"
    r"cannot|can't|never|forbidden|not allowed|bonus|bonuses)\b", re.I)
_SKIPPED_FILES = re.compile(r"readme(?:\.md)?", re.I)      # the README has a check of its own, with its own headings


def _is_file_token(token: str) -> bool:
    return token in BARE_NAMES or bool(re.fullmatch(FILE_NAME, token)) or bool(re.fullmatch(r"(?:[\w.\-]+/)+", token))


def _sentence_files(sentence: str) -> tuple[list[str], bool]:
    """(names, at_the_root) for a sentence that obliges the student to hand in files by name; ([], False) otherwise."""
    s = sentence
    if _NOT_AN_OBLIGATION.search(s) or not _OBLIGED.search(s):
        return [], False
    names: list[str] = []

    def add(name: str) -> None:
        if name and name not in names and not _SKIPPED_FILES.fullmatch(name):
            names.append(name)

    # A Makefile: "submit a Makefile", "turn in your code, a Makefile and ...", "use a Makefile", "A Makefile is also required"
    if (re.search(rf"\b{_HANDED_IN}\s+(?:{_ARTICLE}\s+)?Makefile\b", s, re.I)
            or re.search(rf"\b{_HANDED_IN}\b[^.;:]{{0,60}}\ba\s+Makefile\b", s, re.I)
            or re.search(r"\b(?:use|make|write|create|include)\s+an?\s+Makefile\b", s, re.I)
            or re.search(r"\bA Makefile\b[^.]{0,40}\b(?:is|are)\b[^.]{0,20}\b(?:required|mandatory)\b", s)):
        add("Makefile")
    # "submit a signature.txt file", "provide a data_structures.hpp file", "signature.txt must be present"
    for m in re.finditer(rf"\b{_HANDED_IN}\s+{_ARTICLE}\s+(?:[a-z]+\s+){{0,2}}?(?P<n>{FILE_NAME})\s+file\b", s, re.I):
        add(m.group("n"))
    for m in re.finditer(rf"\b(?P<n>{FILE_NAME})\s+(?:file\s+)?must be (?:present|provided|submitted)\b", s, re.I):
        add(m.group("n"))
    # "a file called author", "a unified header file named libftpp.hpp"
    for m in re.finditer(rf"\b{_HANDED_IN}\b[^.;:]{{0,40}}?\bfile\s+(?:called|named)\s+[`'\"“‘]?(?P<n>{FILE_NAME}|[A-Za-z_][\w\-]{{1,24}})\b", s, re.I):
        add(m.group("n"))
    return names, bool(names) and bool(re.search(r"\bat the root\b", s, re.I))


_LIST_INTRO = re.compile(r"files (?:are|is) (?:mandatory|required)\b|^required files$", re.I)


def _listed_files(lines: list[Line]) -> list[tuple[str, Line]]:
    """Top-level bullets of a list that the subject introduces as its mandatory files ("Required Files"), up to the next
    heading ("Optional but Recommended" is never read)."""
    out: list[tuple[str, Line]] = []
    i = 0
    while i < len(lines):
        if not _LIST_INTRO.search(lines[i].text):
            i += 1
            continue
        seen, j = 0, i + 1
        while j < len(lines):
            text = lines[j].text
            if seen and (re.fullmatch(r"[IVXLC]+(?:\.\d+)*", text) or re.match(r"(optional|recommended)\b", text, re.I)):
                break
            if text.startswith("•"):
                m = re.match(r"•\s*([^\s:—–]+)", text)
                token = m.group(1).rstrip(":,;") if m else ""
                if _is_file_token(token):
                    out.append((token, lines[j]))
                seen += 1
            j += 1
        i = max(j, i + 1)
    return out


_LS_ENTRY = re.compile(r"^([-dl])[rwxsStT-]{9}(?:\s+\S+){7}\s+(\S.*)$")
_LS_HEADER = re.compile(r"^(\.|\./[\w./\-]*):$")


def _layout_files(lines: list[Line]) -> list[tuple[str, Line, bool]]:
    """(path, line, is_example) from a listing of the expected layout: `$> ls -alR` (every file and folder two levels deep),
    or a plain `$> ls` of names, where [bracketed] ones are optional. Only after a sentence about the layout of the repository."""
    out: list[tuple[str, Line, bool]] = []
    for i, line in enumerate(lines):
        if not re.match(r"\$>?\s*ls\b", line.text):
            continue
        context = " ".join(l.text for l in lines[max(0, i - 3): i]).lower()
        if not re.search(r"directory structure|repository layout|layout must|must (?:include|contain)", context):
            continue
        example = "example" in context
        here, j = "", i + 1
        while j < len(lines):
            text = lines[j].text
            m, header = _LS_ENTRY.match(text), _LS_HEADER.match(text)
            if header:
                here = "" if text == ".:" else text[2:-1].rstrip("/") + "/"
            elif m:
                name = m.group(2)
                if name not in (".", ".."):
                    path = here + name + ("/" if m.group(1) == "d" else "")
                    if path.rstrip("/").count("/") <= 1:
                        out.append((path, lines[j], example))
            elif re.match(r"total\b", text):
                pass
            elif re.fullmatch(r"\[?[\w.\-]+/?\]?", text) and "-R" not in line.text:
                if not text.startswith("["):                     # [bracketed] entries are optional; a bare name may be name.md or a folder
                    out.append((text, lines[j], True))
            else:
                break
            j += 1
    return out


def _text_file_rules(hits: list[tuple[list[str], bool, Line]], lines: list[Line], pdf: str, existing: list[Rule]) -> list[Rule]:
    """One `required_files` rule per section from everything the text asks for, minus what a table already asks for."""
    have = {alt for r in existing if r.kind == "required_files" for entry in r.params["files"] for alt in entry}
    found: dict[Section, dict[str, Any]] = {}

    def add(name: str, line: Line, *, root: bool = False, soft: bool = False) -> None:
        if name in have or _SKIPPED_FILES.fullmatch(name.rstrip("/")):
            return
        acc = found.setdefault(line.section, {"files": [], "root": [], "soft": [], "pages": []})
        new = [name] not in acc["files"]
        if new:
            acc["files"].append([name])
        if root and name not in acc["root"]:
            acc["root"].append(name)
        if soft and new:                                  # (only a name first seen in an example is soft)
            acc["soft"].append(name)
        elif not soft and name in acc["soft"]:
            acc["soft"].remove(name)                      # asked for outright elsewhere: not a mere example any more
        if line.page not in acc["pages"]:
            acc["pages"].append(line.page)

    for names, root, line in hits:
        for name in names:
            add(name, line, root=root)
    for name, line in _listed_files(lines):
        add(name, line)
    for name, line, example in _layout_files(lines):
        add(name, line, soft=example)

    rules = []
    for section, acc in found.items():
        params = {"files": acc["files"], "notes": [], **({"root": acc["root"]} if acc["root"] else {}), **({"soft": acc["soft"]} if acc["soft"] else {}),
                  "from_text": True}
        names = ", ".join(e[0] for e in acc["files"])
        rule = _rule("required_files", "Required files named in the subject", text=f"The subject's text asks for: {names}", section=section,
                     params=params, source=Source(pdf=pdf, page=acc["pages"][0]))
        rule.sources = [Source(pdf=pdf, page=p) for p in sorted(acc["pages"])[:3]]
        rules.append(rule)
    return rules


# --------------------------------------------------------------------------- entry points


def parse_subject(pdf: str, pages: list[str]) -> Spec:
    lines = read_lines(pages)
    full = "\n".join(l.text for l in lines)
    module = _cpp_module(pdf, full)

    rules = _parse_tables(lines, pdf) + _cpp_exercise_rules(lines, pdf)
    file_hits: list[tuple[list[str], bool, Line]] = []
    rules += _prose_rules(lines, pdf, module, file_hits)
    rules += _text_file_rules(file_hits, lines, pdf, rules)

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
