"""Suggestions about logic that is likely to fail: results of calls that are never checked. Worded as "possible": a script
cannot prove a bug."""

from __future__ import annotations

import re
from collections.abc import Iterable

from verdict.checks import Ctx, strip_code
from verdict.core.models import Evidence, Improvement
from verdict.reports.improve.heuristic import Heuristic, evidence

ALLOC = re.compile(r"(?:^|[^\w])(\w+)\s*=\s*(?:\([^)]*\)\s*)?(?:malloc|calloc|realloc|ft_calloc|strdup|ft_strdup|ft_substr|ft_strjoin|ft_split)\s*\(")
OPEN = re.compile(r"(?:^|[^\w])(\w+)\s*=\s*open\s*\(")
MAX_HITS = 12
WINDOW = 5      # lines after the call in which the result must be checked


def checked(var: str, following: list[str]) -> bool:
    pattern = re.compile(rf"(!\s*\(?\s*{re.escape(var)}\b|\b{re.escape(var)}\s*(==|<|<=)\s*(NULL|0|-1|nullptr)\b|\b(NULL|0|-1)\s*(==|>)\s*{re.escape(var)}\b|\bif\s*\(\s*{re.escape(var)}\s*\)|\b{re.escape(var)}\s*\?)")
    return any(pattern.search(line) for line in following)


class LogicHeuristic(Heuristic):
    def improvements(self, ctx: Ctx) -> Iterable[Improvement]:
        unchecked_alloc: list[Evidence] = []
        unchecked_open: list[Evidence] = []
        for rel in ctx.source_files():
            if rel.suffix not in (".c", ".cpp", ".cc"):
                continue
            raw_lines = ctx.read(rel).splitlines()
            code_lines = strip_code("\n".join(raw_lines)).split("\n")
            for index, line in enumerate(code_lines):
                window = code_lines[index + 1:index + 1 + WINDOW]
                for pattern, hits in ((ALLOC, unchecked_alloc), (OPEN, unchecked_open)):
                    m = pattern.search(line)
                    if m and not checked(m.group(1), window) and len(hits) < MAX_HITS:
                        hits.append(evidence(rel, index + 1, raw_lines[index].strip()))
        if unchecked_alloc:
            yield Improvement(category="logic", priority="high", title="Possible unchecked allocation",
                              detail="These allocations are not followed by a NULL check within a few lines. A failed malloc would "
                                     "crash with a segfault; check the result and free what was already allocated before returning.",
                              evidence=unchecked_alloc)
        if unchecked_open:
            yield Improvement(category="logic", priority="medium", title="Possible unchecked open()",
                              detail="open() returns -1 on failure; the result is not compared within a few lines.", evidence=unchecked_open)
