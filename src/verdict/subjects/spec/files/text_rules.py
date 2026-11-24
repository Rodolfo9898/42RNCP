from __future__ import annotations

from dataclasses import dataclass, field

from verdict.core.models import Rule, Section, Source
from verdict.subjects.spec.files.listings import layout_files, listed_files
from verdict.subjects.spec.files.sentences import SKIPPED_FILES
from verdict.subjects.spec.model import Line, make_rule

FileHit = tuple[list[str], bool, Line]          # (names, at_the_root, the line that says it), from a sentence


@dataclass
class Wanted:
    """What the text of one part (mandatory or bonus) asks for."""

    files: list[list[str]] = field(default_factory=list)
    root: list[str] = field(default_factory=list)
    soft: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)


class TextFileRules:
    """Builder of the `required_files` rules asked for by the text: one rule per part, from everything the text names, minus what a
    table already asks for (`have`)."""

    def __init__(self, pdf: str, have: set[str]) -> None:
        self.pdf, self.have = pdf, have
        self.found: dict[Section, Wanted] = {}

    def add(self, name: str, line: Line, *, root: bool = False, soft: bool = False) -> None:
        if name in self.have or SKIPPED_FILES.fullmatch(name.rstrip("/")):
            return
        acc = self.found.setdefault(line.section, Wanted())
        new = [name] not in acc.files
        if new:
            acc.files.append([name])
        if root and name not in acc.root:
            acc.root.append(name)
        if soft and new:                                  # (only a name first seen in an example is soft)
            acc.soft.append(name)
        elif not soft and name in acc.soft:
            acc.soft.remove(name)                         # asked for outright elsewhere: not a mere example any more
        if line.page not in acc.pages:
            acc.pages.append(line.page)

    def collect(self, hits: list[FileHit], lines: list[Line]) -> TextFileRules:
        for names, root, line in hits:
            for name in names:
                self.add(name, line, root=root)
        for name, line in listed_files(lines):
            self.add(name, line)
        for name, line, example in layout_files(lines):
            self.add(name, line, soft=example)
        return self

    def build(self) -> list[Rule]:
        return [self._rule(section, acc) for section, acc in self.found.items()]

    def _rule(self, section: Section, acc: Wanted) -> Rule:
        params = {"files": acc.files, "notes": [], **({"root": acc.root} if acc.root else {}), **({"soft": acc.soft} if acc.soft else {}),
                  "from_text": True}
        names = ", ".join(e[0] for e in acc.files)
        rule = make_rule("required_files", "Required files named in the subject", text=f"The subject's text asks for: {names}", section=section,
                         params=params, source=Source(pdf=self.pdf, page=acc.pages[0]))
        rule.sources = [Source(pdf=self.pdf, page=p) for p in sorted(acc.pages)[:3]]
        return rule


def text_file_rules(hits: list[FileHit], lines: list[Line], pdf: str, existing: list[Rule]) -> list[Rule]:
    """One `required_files` rule per section from everything the text asks for, minus what a table already asks for."""
    have = {alt for r in existing if r.kind == "required_files" for entry in r.params["files"] for alt in entry}
    return TextFileRules(pdf, have).collect(hits, lines).build()
