from __future__ import annotations

import re

from verdict.core.models import Rule, Source
from verdict.subjects.spec.files import expand_files, file_params
from verdict.subjects.spec.model import Line, make_rule
from verdict.subjects.spec.vocabulary import DEFAULT_MAKEFILE_RULES


def _files_to_submit(lines: list[Line], j: int) -> tuple[str, int]:
    """The value of the `Files to Submit:` lines from `j` (a value ending with a comma goes on in the next line), and the index after them."""
    files = ""
    while j < len(lines) and lines[j].text.lower().startswith("files to submit:"):
        files = lines[j].text.split(":", 1)[1].strip()
        while files.endswith(",") and j + 1 < len(lines):
            j += 1
            files += " " + lines[j].text
        j += 1
    return files, j


def cpp_exercise_rules(lines: list[Line], source_pdf: str) -> list[Rule]:
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
        files, i = _files_to_submit(lines, i + 1)
        required, notes = expand_files(files)
        if required:
            rules.append(make_rule("required_files", "Required files", text=f"Files to submit: {files}",
                                   section=section, unit=unit, params=file_params(required, notes), source=source))
        rules.append(make_rule("build_unit", f"{unit}: compiles", text=f"Exercise {unit}", section=section,
                               unit=unit, params={}, source=source))
        rules.append(make_rule("makefile_rules", "Makefile rules", text="Makefile rules (same rules as C)", section=section,
                               unit=unit, params={"targets": DEFAULT_MAKEFILE_RULES}, source=source))
    return rules
