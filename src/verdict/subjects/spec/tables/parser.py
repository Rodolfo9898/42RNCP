from __future__ import annotations

from verdict.core.models import Rule, Source
from verdict.subjects.spec.model import Line
from verdict.subjects.spec.tables.fields import TABLE_STARTS, read_table
from verdict.subjects.spec.tables.functions import FunctionTables
from verdict.subjects.spec.tables.programs import ProgramRules
from verdict.subjects.spec.vocabulary import label_of


class TableParser:
    """Reads the field tables of a subject. A program table gives its rules at once; the tables of a function-style subject are handed
    to `FunctionTables`, which sums them up at the end."""

    def __init__(self, lines: list[Line], pdf: str) -> None:
        self.lines, self.pdf = lines, pdf
        self.functions = FunctionTables(lines, pdf)

    def parse(self) -> list[Rule]:
        rules: list[Rule] = []
        i = 0
        while i < len(self.lines):
            first = label_of(self.lines[i].text)
            if first not in TABLE_STARTS:
                i += 1
                continue
            start = self.lines[i]
            fields, j = read_table(self.lines, i)
            source = Source(pdf=self.pdf, page=start.page)
            if first == "program":
                rules += ProgramRules(fields, start.section, source).rules()
                self.functions.is_libft = self.functions.is_libft or fields.get("program", "").strip() == "libft.a"
            else:
                rules += self.functions.add(fields, start.section, source)
            i = max(j, i + 1)
        return rules + self.functions.summary()


def parse_tables(lines: list[Line], pdf: str) -> list[Rule]:
    return TableParser(lines, pdf).parse()
