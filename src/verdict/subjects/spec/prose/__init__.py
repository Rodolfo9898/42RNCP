"""The prose of a subject: sentences, the chain of extractors that recognise requirements in them, and the pass that reads it all."""

from verdict.subjects.spec.prose.chain import ExtractorChain, default_chain
from verdict.subjects.spec.prose.extractors import PatternExtractor, RuleExtractor
from verdict.subjects.spec.prose.items import line_of, prose_items
from verdict.subjects.spec.prose.reader import ProseReader
from verdict.subjects.spec.prose.sentence import Sentence, cpp_module

__all__ = ["ExtractorChain", "PatternExtractor", "ProseReader", "RuleExtractor", "Sentence", "cpp_module", "default_chain",
           "line_of", "prose_items"]
