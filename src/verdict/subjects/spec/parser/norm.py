from __future__ import annotations

import re

from verdict.core.models import Source
from verdict.subjects.spec.lines import read_lines
from verdict.subjects.spec.model import Spec, make_rule, merge_rules
from verdict.subjects.spec.prose import prose_items

STARRED = re.compile(r"(?:[-•◦]\s*)?\(\*\)\s*(.+)")


class NormParser:
    """The Norm (en.norm.pdf): norminette checks most of it; the rules it marks with (*) need a human."""

    def parse(self, pdf: str, pages: list[str]) -> Spec:
        lines = read_lines(pages)
        first = next((l for l in lines if "norminette" in l.text.lower()), lines[0] if lines else None)
        rules = [make_rule("norm", "Passes norminette", text="The code must follow the Norm (checked by norminette).",
                           source=Source(pdf=pdf, page=first.page) if first else None)]
        for sentence, line in prose_items(lines):
            m = STARRED.match(sentence)
            if m:
                text = m.group(1)
                rules.append(make_rule("manual", "Norm rule norminette cannot check", text=text, params={"text": text},
                                       source=Source(pdf=pdf, page=line.page)))
        return Spec(name=pdf, lang="c", rules=merge_rules(rules))


def parse_norm(pdf: str, pages: list[str]) -> Spec:
    return NormParser().parse(pdf, pages)
