from __future__ import annotations

import re

from verdict.core.models import Rule, Source
from verdict.subjects.spec.files import FileHit, sentence_files
from verdict.subjects.spec.model import Line, make_rule
from verdict.subjects.spec.prose.chain import ExtractorChain
from verdict.subjects.spec.prose.items import line_of, prose_items
from verdict.subjects.spec.prose.sentence import Sentence
from verdict.subjects.spec.vocabulary import ABOUT_THE_SUBJECT, REQUIREMENT_WORDS, SKIPPED_CHAPTERS

TURN_IN_CHAPTER = re.compile(r"submission|turn-?in")


class ProseReader:
    """Reads the prose of a subject, in the chapters that can hold requirements. Each sentence goes down the chain of extractors; one
    the chain does not take either names files to hand in (kept apart, for the rules of the files the text asks for), or states a
    requirement no script can check (a manual rule), or says nothing."""

    def __init__(self, chain: ExtractorChain, lines: list[Line], pdf: str, module: int | None) -> None:
        self.chain, self.lines, self.pdf, self.module = chain, lines, pdf, module

    def read(self) -> tuple[list[Rule], list[FileHit]]:
        """(the rules, the file names the sentences ask for)."""
        # The chapter about turning in the work is skipped for vague requirements, but it is where some subjects say what to turn in.
        turn_in = [l for l in self.lines if TURN_IN_CHAPTER.search(l.chapter)]
        hits = [hit for text, line in prose_items(turn_in) if (hit := self._file_hit(text, line, turn_in))]
        prose = [l for l in self.lines if not any(c in l.chapter for c in SKIPPED_CHAPTERS)]
        rules: list[Rule] = []
        for text, line in prose_items(prose):
            sentence = Sentence(text, line, self.pdf, self.module)
            rule = self.chain.rule_for(sentence)
            if rule is None and (hit := self._file_hit(text, line, prose)):
                hits.append(hit)                       # "You must submit a Makefile": a required file, not a vague manual item
                continue
            rule = rule or self._manual(sentence)
            if rule is not None:
                rules.append(rule)
        return rules, hits

    @staticmethod
    def _file_hit(text: str, line: Line, within: list[Line]) -> FileHit | None:
        names, root = sentence_files(text)
        return (names, root, line_of(within, line, names[0])) if names else None

    def _manual(self, sentence: Sentence) -> Rule | None:
        if not REQUIREMENT_WORDS.search(sentence.text) or ABOUT_THE_SUBJECT.search(sentence.text):
            return None
        return make_rule("manual", "Needs manual review", text=sentence.text, section=sentence.line.section,
                         params={"text": sentence.text}, source=Source(pdf=self.pdf, page=sentence.line.page))
