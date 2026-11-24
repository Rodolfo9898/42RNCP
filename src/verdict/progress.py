"""Progress.md: the table of which projects have been run through Verdict and what came out.

    | Project | Run |
    |---|:---:|
    | libft | ✅ |

One row per project, in alphabetical order, with ✅ (PASS), ⚠️ (PASS WITH ISSUES), ❌ (FAIL) or ⬜ (not run). Only the row of the project
being updated changes: the text around the table (what the symbols mean, anything the person wrote) is kept exactly as it is.
"""

from __future__ import annotations

import re

SYMBOLS = {"PASS": "✅", "PASS WITH ISSUES": "⚠️", "FAIL": "❌"}
NOT_RUN = "⬜"
HEADER = "| Project | Run |"
RULER = "|---|:---:|"
ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$")
INTRO = ("# Projects\n\nWhich projects have been run through Verdict and what came out. Update the row when a project is run again (the result\n"
         "is the one at the top of its `verdict.md`).\n\n")
LEGEND = "\n✅ run and accepted (`PASS`) · ⚠️ run, `PASS WITH ISSUES` (not accepted yet) · ❌ run, `FAIL` · ⬜ not run\n"


class ProgressError(ValueError):
    pass


def symbol_for(result: str) -> str:
    """The symbol of a verdict result. Only a real result has one: a project that was not run is not marked."""
    try:
        return SYMBOLS[result]
    except KeyError:
        raise ProgressError(f"there is no result to record yet (it says {result or 'nothing'}): run the checks first") from None


def _is_row(line: str) -> bool:
    return bool(ROW.match(line)) and not set(line.replace("|", "").strip()) <= set("-: ")


def update(text: str, project: str, symbol: str) -> tuple[str, str | None]:
    """The text with the row of `project` set to `symbol` (added in its alphabetical place when it has none), and what the row said before
    (None for a new row). The rest of the text is returned untouched."""
    if not re.fullmatch(r"[\w.\-]+", project):
        raise ProgressError(f"{project!r} is not a project name that can go in the table")
    lines = text.split("\n")
    rows = [i for i, line in enumerate(lines) if _is_row(line) and ROW.match(line).group(1).lower() != "project"]
    for i in rows:
        name, old = ROW.match(lines[i]).groups()
        if name.lower() == project.lower():
            lines[i] = f"| {name} | {symbol} |"
            return "\n".join(lines), old
    new = f"| {project} | {symbol} |"
    if not rows:                                            # no table yet (a new or empty file): start one
        head = text if text.strip() else INTRO
        body = head.rstrip("\n") + "\n\n" + "\n".join([HEADER, RULER, new]) + "\n"
        return (body + LEGEND if not text.strip() else body), None
    after = next((i for i in rows if ROW.match(lines[i]).group(1).lower() > project.lower()), None)
    lines.insert(after if after is not None else rows[-1] + 1, new)
    return "\n".join(lines), None
