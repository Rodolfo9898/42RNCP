from __future__ import annotations

import re

from verdict.core.models import Rule
from verdict.subjects.spec.files import text_file_rules
from verdict.subjects.spec.lines import read_lines
from verdict.subjects.spec.model import Spec, merge_rules
from verdict.subjects.spec.prose import ExtractorChain, ProseReader, cpp_module, default_chain
from verdict.subjects.spec.tables import cpp_exercise_rules, parse_tables


class SubjectParser:
    """The rules of a subject PDF, from its pages (Facade over the readers): the field tables, the C++ exercises, the general
    rules in the prose (through the chain of extractors it is given) and the files the text asks for outside any table."""

    def __init__(self, chain: ExtractorChain | None = None) -> None:
        self.chain = chain or default_chain()

    def parse(self, pdf: str, pages: list[str]) -> Spec:
        lines = read_lines(pages)
        full = "\n".join(l.text for l in lines)
        rules = parse_tables(lines, pdf) + cpp_exercise_rules(lines, pdf)
        prose, file_hits = ProseReader(self.chain, lines, pdf, cpp_module(pdf, full)).read()
        rules += prose
        rules += text_file_rules(file_hits, lines, pdf, rules)
        return Spec(name=pdf, lang=self._language(rules, full), rules=merge_rules(rules))

    @staticmethod
    def _language(rules: list[Rule], text: str) -> str | None:
        if any(r.kind == "std98" for r in rules):
            return "cpp"
        return "c" if re.search(r"must be written in C\b", text) else None


def parse_subject(pdf: str, pages: list[str]) -> Spec:
    return SubjectParser().parse(pdf, pages)
