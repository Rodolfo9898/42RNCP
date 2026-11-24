from __future__ import annotations

from verdict.subjects.spec.model import Line
from verdict.subjects.spec.vocabulary import label_of

TABLE_STARTS = ("program", "function_name")      # a table opens with the name of the program or of the function it describes


def read_table(lines: list[Line], start: int) -> tuple[dict[str, str], int]:
    """The fields of the table that opens at `start`, each one's lines joined, and the index of the first line after the table.
    A table runs from its first label to the `Description` label (or to the first line that belongs to no field)."""
    fields: dict[str, list[str]] = {}
    current = None
    j = start
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
    return {k: " ".join(v).strip() for k, v in fields.items()}, j
