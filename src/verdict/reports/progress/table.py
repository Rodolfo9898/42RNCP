"""Progress.md: the table of which projects have been run through Verdict and what came out.

    | Project | Run |
    |---|:---:|
    | libft | ✅ |

One row per project, in alphabetical order, with ✅ (PASS), ⚠️ (PASS WITH ISSUES), ❌ (FAIL) or ⬜ (not run). Only the row of the project
being updated changes: the text around the table (what the symbols mean, anything the person wrote) is kept exactly as it is.
"""

from __future__ import annotations

import re

from verdict.reports.progress.symbols import ProgressError

HEADER = "| Project | Run |"
RULER = "|---|:---:|"
ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$")
INTRO = ("# Projects\n\nWhich projects have been run through Verdict and what came out. Update the row when a project is run again (the result\n"
         "is the one at the top of its `verdict.md`).\n\n")
LEGEND = "\n✅ run and accepted (`PASS`) · ⚠️ run, `PASS WITH ISSUES` (not accepted yet) · ❌ run, `FAIL` · ⬜ not run\n"


def is_row(line: str) -> bool:
    return bool(ROW.match(line)) and not set(line.replace("|", "").strip()) <= set("-: ")


class ProgressTable:
    """The text of Progress.md, and the one row of it that a run changes (everything else is returned untouched)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.lines = text.split("\n")
        self.rows = [i for i, line in enumerate(self.lines) if is_row(line) and ROW.match(line).group(1).lower() != "project"]

    def update(self, project: str, symbol: str) -> tuple[str, str | None]:
        """The text with the row of `project` set to `symbol` (added in its alphabetical place when it has none), and what the row
        said before (None for a new row)."""
        if not re.fullmatch(r"[\w.\-]+", project):
            raise ProgressError(f"{project!r} is not a project name that can go in the table")
        for i in self.rows:
            name, old = ROW.match(self.lines[i]).groups()
            if name.lower() == project.lower():
                self.lines[i] = f"| {name} | {symbol} |"
                return "\n".join(self.lines), old
        new = f"| {project} | {symbol} |"
        if not self.rows:                                   # no table yet (a new or empty file): start one
            return self._start(new), None
        after = next((i for i in self.rows if ROW.match(self.lines[i]).group(1).lower() > project.lower()), None)
        self.lines.insert(after if after is not None else self.rows[-1] + 1, new)
        return "\n".join(self.lines), None

    def _start(self, row: str) -> str:
        head = self.text if self.text.strip() else INTRO
        body = head.rstrip("\n") + "\n\n" + "\n".join([HEADER, RULER, row]) + "\n"
        return body + LEGEND if not self.text.strip() else body


def update(text: str, project: str, symbol: str) -> tuple[str, str | None]:
    """The text with the row of `project` set to `symbol` (added in its alphabetical place when it has none), and what the row said before
    (None for a new row). The rest of the text is returned untouched."""
    return ProgressTable(text).update(project, symbol)
