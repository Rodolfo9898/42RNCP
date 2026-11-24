from __future__ import annotations

from collections.abc import Sequence

from verdict.core.models import Rule
from verdict.subjects.spec.prose import extractors as kinds
from verdict.subjects.spec.prose.extractors import RuleExtractor
from verdict.subjects.spec.prose.sentence import Sentence


class ExtractorChain:
    """Chain of Responsibility: the extractors in order, and the first one that recognises a sentence makes its rule. The order is
    part of the meaning (a sentence about the Makefile's flags is never also read as one about the Makefile's rules)."""

    def __init__(self, extractors: Sequence[RuleExtractor]) -> None:
        self.extractors = tuple(extractors)

    def rule_for(self, sentence: Sentence) -> Rule | None:
        for extractor in self.extractors:
            rule = extractor.extract(sentence)
            if rule is not None:
                return rule
        return None


def default_chain() -> ExtractorChain:
    """The requirements the 42 subjects state in their general rules, in the order they are tried."""
    return ExtractorChain([
        kinds.Flags(), kinds.Std98(), kinds.Norm(), kinds.NoRelink(), kinds.MakefileRules(), kinds.NoCrash(), kinds.WrittenInC(),
        kinds.NoLeaks(), kinds.NoGlobals(), kinds.BonusRule(), kinds.CppForbiddenCalls(), kinds.CppForbiddenKeywords(),
        kinds.CppNoStl(), kinds.Readme(), kinds.IncludeGuards(), kinds.LibftCopy(),
    ])
