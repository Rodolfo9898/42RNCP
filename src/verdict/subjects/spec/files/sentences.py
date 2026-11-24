"""Files the subject names in its sentences instead of in a table.

Most subjects give their files in a table ("Files to Submit"), but many only say it in the text: "You must submit a Makefile",
"a signature.txt file at the root of your repository". Those become required files too, under strict conditions: an obligation
(must, have to, required, ...) that names a concrete file, never a condition ("if you use ..."), an example, something optional,
something forbidden or a bonus.
"""

from __future__ import annotations

import re

FILE_NAME = r"(?:[\w.\-]+/)*[A-Za-z0-9_][\w.\-]*\.[A-Za-z][A-Za-z0-9]{0,5}"
BARE_NAMES = {"Makefile", "Dockerfile"}
_HANDED_IN = r"(?:submit|turn[- ]?in|hand in|provide|deposit|ship|deliver)"
_ARTICLE = r"(?:an?|the|your|its)"
_OBLIGED = re.compile(r"\b(must|have to|has to|need to|needs to|required|mandatory|expected to|should)\b", re.I)
_NOT_AN_OBLIGATION = re.compile(
    r"\b(if|unless|optional|optionally|example|e\.g\.|for instance|such as|similar|do not|don't|must not|should not|shouldn't|"
    r"cannot|can't|never|forbidden|not allowed|bonus|bonuses)\b", re.I)
SKIPPED_FILES = re.compile(r"readme(?:\.md)?", re.I)      # the README has a check of its own, with its own headings


def is_file_token(token: str) -> bool:
    return token in BARE_NAMES or bool(re.fullmatch(FILE_NAME, token)) or bool(re.fullmatch(r"(?:[\w.\-]+/)+", token))


def _asks_for_makefile(s: str) -> bool:
    """A Makefile: "submit a Makefile", "turn in your code, a Makefile and ...", "use a Makefile", "A Makefile is also required"."""
    return bool(re.search(rf"\b{_HANDED_IN}\s+(?:{_ARTICLE}\s+)?Makefile\b", s, re.I)
                or re.search(rf"\b{_HANDED_IN}\b[^.;:]{{0,60}}\ba\s+Makefile\b", s, re.I)
                or re.search(r"\b(?:use|make|write|create|include)\s+an?\s+Makefile\b", s, re.I)
                or re.search(r"\bA Makefile\b[^.]{0,40}\b(?:is|are)\b[^.]{0,20}\b(?:required|mandatory)\b", s))


def _named_files(s: str) -> list[str]:
    """Every file name the sentence hands in, in the order of the patterns below (duplicates and the README are dealt with by the caller)."""
    found: list[str] = []
    # "submit a signature.txt file", "provide a data_structures.hpp file", "signature.txt must be present"
    for m in re.finditer(rf"\b{_HANDED_IN}\s+{_ARTICLE}\s+(?:[a-z]+\s+){{0,2}}?(?P<n>{FILE_NAME})\s+file\b", s, re.I):
        found.append(m.group("n"))
    for m in re.finditer(rf"\b(?P<n>{FILE_NAME})\s+(?:file\s+)?must be (?:present|provided|submitted)\b", s, re.I):
        found.append(m.group("n"))
    # "a file called author", "a unified header file named libftpp.hpp"
    for m in re.finditer(rf"\b{_HANDED_IN}\b[^.;:]{{0,40}}?\bfile\s+(?:called|named)\s+[`'\"“‘]?(?P<n>{FILE_NAME}|[A-Za-z_][\w\-]{{1,24}})\b", s, re.I):
        found.append(m.group("n"))
    return found


def sentence_files(sentence: str) -> tuple[list[str], bool]:
    """(names, at_the_root) for a sentence that obliges the student to hand in files by name; ([], False) otherwise."""
    s = sentence
    if _NOT_AN_OBLIGATION.search(s) or not _OBLIGED.search(s):
        return [], False
    names: list[str] = []
    for name in (["Makefile"] if _asks_for_makefile(s) else []) + _named_files(s):
        if name and name not in names and not SKIPPED_FILES.fullmatch(name):
            names.append(name)
    return names, bool(names) and bool(re.search(r"\bat the root\b", s, re.I))
