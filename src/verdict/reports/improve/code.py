"""Suggestions about the code and how readable it is: long functions and files, nesting, leftover debugging, unsafe calls."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from verdict.checks import Ctx, strip_code
from verdict.core.models import Evidence, Improvement
from verdict.reports.improve.functions import functions
from verdict.reports.improve.heuristic import Heuristic, evidence

LONG_FUNCTION = 40
LONG_FILE = 500
LONG_LINE = 120
MAX_NESTING = 5
MAX_HITS = 10
DEBUG_PRINT = re.compile(r"printf\s*\(\s*\"\s*(\[?debug|here|test|\w*\bDEBUG)", re.I)
NOTE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
COMMENTED_CODE = re.compile(r"^\s*//\s*(\w+\s*\(.*\)\s*;|[\w\->.\[\]]+\s*=\s*.+;|\}|\{|if\s*\(|while\s*\(|return\b.*;)\s*$")
UNSAFE_CALL = re.compile(r"(?<![\w.>])(gets|strcpy|strcat|sprintf|system)\s*\(")


@dataclass
class Line:
    """A line of a source file, as written and with comments and strings blanked out."""

    file: Path
    number: int
    raw: str
    code: str
    lang: str | None


class LineRule:
    """Strategy: whether a line is worth reporting (`test` gives what to show for it, or None), keeping the first few that are."""

    def __init__(self, test: Callable[[Line], str | None]) -> None:
        self.test = test
        self.hits: list[Evidence] = []

    def scan(self, line: Line) -> None:
        if len(self.hits) < MAX_HITS and (snippet := self.test(line)) is not None:
            self.hits.append(evidence(line.file, line.number, snippet))


def _too_wide(line: Line) -> str | None:
    width = len(line.raw.expandtabs(4))
    return f"{width} columns" if width > LONG_LINE and line.lang == "cpp" else None


def _deeply_nested(line: Line) -> str | None:
    indent = len(line.raw) - len(line.raw.lstrip("\t"))
    return line.raw.strip() if line.code.strip() and indent > MAX_NESTING else None


def _matching(pattern: re.Pattern[str], *, on_code: bool = False, suffixes: tuple[str, ...] = ()) -> Callable[[Line], str | None]:
    def test(line: Line) -> str | None:
        if suffixes and line.file.suffix not in suffixes:
            return None
        return line.raw.strip() if pattern.search(line.code if on_code else line.raw) else None
    return test


class CodeHeuristic(Heuristic):
    def improvements(self, ctx: Ctx) -> Iterable[Improvement]:
        rules = {"wide": LineRule(_too_wide), "deep": LineRule(_deeply_nested), "debug": LineRule(_matching(DEBUG_PRINT)),
                 "todo": LineRule(_matching(NOTE)), "dead": LineRule(_matching(COMMENTED_CODE)),
                 "unsafe": LineRule(_matching(UNSAFE_CALL, on_code=True, suffixes=(".c", ".h")))}
        long_functions: list[tuple[int, str, str, int]] = []
        long_files: list[tuple[int, str]] = []
        for rel in ctx.source_files():
            raw = ctx.read(rel)
            raw_lines = raw.splitlines()
            if len(raw_lines) > LONG_FILE:
                long_files.append((len(raw_lines), rel.as_posix()))
            code = strip_code(raw)
            long_functions += [(last - first - 1, name, rel.as_posix(), first) for name, first, last in functions(code)
                               if last - first - 1 > LONG_FUNCTION]
            for number, (raw_line, code_line) in enumerate(zip(raw_lines, code.split("\n")), 1):
                for rule in rules.values():
                    rule.scan(Line(rel, number, raw_line, code_line, ctx.lang))
        yield from self._report(long_functions, long_files, {name: rule.hits for name, rule in rules.items()})

    @staticmethod
    def _report(long_functions: list, long_files: list, hits: dict[str, list[Evidence]]) -> Iterable[Improvement]:
        if long_functions:
            long_functions.sort(reverse=True)
            yield Improvement(category="readability", priority="medium", title=f"{len(long_functions)} very long function(s)",
                              detail=f"Functions longer than {LONG_FUNCTION} lines are hard to read and test. Split them into small helpers "
                                     "that each do one thing (the Norm already limits C functions to 25 lines).",
                              evidence=[evidence(f, line, f"{name}(): {size} lines") for size, name, f, line in long_functions[:8]])
        if long_files:
            long_files.sort(reverse=True)
            yield Improvement(category="structure", priority="low", title="Very long source files",
                              detail=f"Files over {LONG_FILE} lines usually mix several responsibilities; split them by topic.",
                              evidence=[evidence(f, snippet=f"{n} lines") for n, f in long_files[:6]])
        if hits["deep"]:
            yield Improvement(category="readability", priority="medium", title="Deeply nested code",
                              detail=f"More than {MAX_NESTING} levels of indentation. Return early, or move the inner block into a function.",
                              evidence=hits["deep"])
        if hits["wide"]:
            yield Improvement(category="readability", priority="low", title="Very long lines",
                              detail=f"Lines wider than {LONG_LINE} columns are hard to review.", evidence=hits["wide"])
        yield from CodeHeuristic._code_notes(hits)

    @staticmethod
    def _code_notes(hits: dict[str, list[Evidence]]) -> Iterable[Improvement]:
        if hits["debug"]:
            yield Improvement(category="code", priority="medium", title="Debug output left in the code",
                              detail="Remove debugging prints (or hide them behind a macro) before submitting.", evidence=hits["debug"])
        if hits["dead"]:
            yield Improvement(category="code", priority="low", title="Commented-out code",
                              detail="Delete dead code instead of commenting it out; git remembers it.", evidence=hits["dead"])
        if hits["todo"]:
            yield Improvement(category="code", priority="low", title="Unresolved TODO/FIXME notes", detail="", evidence=hits["todo"])
        if hits["unsafe"]:
            yield Improvement(category="code", priority="medium", title="Functions that are easy to misuse",
                              detail="gets, strcpy, strcat and sprintf do no bounds checking and system() runs a shell. "
                                     "Use sized alternatives (or your own checked helpers), and check whether the subject allows them at all.",
                              evidence=hits["unsafe"])
