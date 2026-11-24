"""The 'Files to Submit' value of a table: `Makefile, *.h, *.{h, hpp}, ft_*.c, all at the root of the repository`."""

from __future__ import annotations

import re
from typing import Any


def file_params(required: list[list[str]], notes: list[str]) -> dict[str, Any]:
    """The parameters of a required_files rule. A note such as "all at the root of the repository" is a requirement too: the files
    it covers must be at the root, not merely somewhere in the project."""
    params: dict[str, Any] = {"files": required, "notes": notes}
    if any(re.search(r"\bat the root\b", note, re.I) for note in notes):
        params["root"] = [alt for entry in required for alt in entry]
    return params


def root_or_subfolder(required: list[list[str]]) -> list[list[str]]:
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
    return root_or_subfolder(required), notes
