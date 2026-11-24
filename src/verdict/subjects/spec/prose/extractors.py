from __future__ import annotations

import re
from typing import Any

from verdict.core.models import Rule
from verdict.subjects.spec.model import make_rule
from verdict.subjects.spec.prose.sentence import Sentence
from verdict.subjects.spec.vocabulary import DEFAULT_MAKEFILE_RULES


class RuleExtractor:
    """One kind of requirement a subject's sentence can state (Template Method: a subclass says when a sentence is its kind and
    which parameters the rule gets; making the rule is the same for all of them)."""

    kind: str
    title: str

    def matches(self, sentence: Sentence) -> bool:
        raise NotImplementedError

    def params(self, sentence: Sentence) -> dict[str, Any]:
        return {}

    def extract(self, sentence: Sentence) -> Rule | None:
        if not self.matches(sentence):
            return None
        return make_rule(self.kind, self.title, text=sentence.text, section=sentence.line.section,
                         params=self.params(sentence), source=sentence.source)


class PatternExtractor(RuleExtractor):
    """An extractor for sentences in which `pattern` is found (read in lower case)."""

    pattern: re.Pattern[str]

    def matches(self, sentence: Sentence) -> bool:
        return bool(self.pattern.search(sentence.low))


class Flags(RuleExtractor):
    kind, title = "flags", "Compiles with -Wall -Wextra -Werror"

    def matches(self, sentence: Sentence) -> bool:
        return bool(re.search(r"-Wall.*-Wextra.*-Werror", sentence.text))

    def params(self, sentence: Sentence) -> dict[str, Any]:
        low = sentence.low
        compiler = "c++" if re.search(r"\bc\+\+\b", low) and "cc" not in re.findall(r"\bcc\b", low) else "cc"
        return {"flags": ["-Wall", "-Wextra", "-Werror"], "compiler": compiler}


class Std98(RuleExtractor):
    kind, title = "std98", "Still compiles with -std=c++98"

    def matches(self, sentence: Sentence) -> bool:
        return "-std=c++98" in sentence.text


class Norm(PatternExtractor):
    kind, title = "norm", "Passes norminette"
    pattern = re.compile(r"accordance with the norm|follow the norm")

    def matches(self, sentence: Sentence) -> bool:
        return super().matches(sentence) and "goodbye" not in sentence.low


class NoRelink(RuleExtractor):
    kind, title = "no_relink", "Makefile does not relink"

    def matches(self, sentence: Sentence) -> bool:
        return "unnecessary relinking" in sentence.low


class MakefileRules(PatternExtractor):
    kind, title = "makefile_rules", "Makefile rules"
    pattern = re.compile(r"makefile must contain at least the rules")

    def params(self, sentence: Sentence) -> dict[str, Any]:
        return {"targets": DEFAULT_MAKEFILE_RULES}


class NoCrash(PatternExtractor):
    kind, title = "no_crash", "Does not crash"
    pattern = re.compile(r"quit unexpectedly|segmentation fault")


class WrittenInC(PatternExtractor):
    kind, title = "language", "Written in C"
    pattern = re.compile(r"must be written in c\b")

    def params(self, sentence: Sentence) -> dict[str, Any]:
        return {"lang": "c"}


class NoLeaks(PatternExtractor):
    kind, title = "no_leaks", "No memory leaks"
    pattern = re.compile(r"memory leak|properly freed")


class NoGlobals(RuleExtractor):
    kind, title = "no_globals", "No global variables"

    def matches(self, sentence: Sentence) -> bool:
        low = sentence.low
        return bool(re.search(r"global variables?", low) and re.search(r"forbidden|not allowed", low) and "one global" not in low)


class BonusRule(RuleExtractor):
    kind, title = "bonus_rule", "Makefile has a bonus rule"

    def matches(self, sentence: Sentence) -> bool:
        return "bonus rule" in sentence.low and "makefile" in sentence.low


class CppForbiddenCalls(RuleExtractor):
    kind, title = "cpp_forbidden_calls", "No *printf(), *alloc() or free()"

    def matches(self, sentence: Sentence) -> bool:
        return bool(re.search(r"\*printf\(\).*\*alloc\(\).*free\(\)", sentence.text) or re.search(r"printf.*alloc.*free.*forbidden", sentence.low))

    def params(self, sentence: Sentence) -> dict[str, Any]:
        return {"names": ["printf", "alloc", "free"]}


class CppForbiddenKeywords(RuleExtractor):
    kind, title = "cpp_forbidden_keywords", "No `using namespace` or `friend`"

    def matches(self, sentence: Sentence) -> bool:
        low = sentence.low
        return "using namespace" in low and "friend" in low and "forbidden" in low


class CppNoStl(PatternExtractor):
    kind, title = "cpp_no_stl", "No STL containers/algorithms before module 08"
    pattern = re.compile(r"stl only in modules?")

    def params(self, sentence: Sentence) -> dict[str, Any]:
        return {"module": sentence.module}


class Readme(PatternExtractor):
    kind, title = "readme", "README.md meets the subject's requirements"
    pattern = re.compile(r"readme\.md.*must be provided|readme\.md must include|first line must be italicized")

    def params(self, sentence: Sentence) -> dict[str, Any]:
        return {"sections": ["Description", "Instructions", "Resources"]}


class IncludeGuards(RuleExtractor):
    kind, title = "include_guards", "Headers have include guards"

    def matches(self, sentence: Sentence) -> bool:
        return "include guards" in sentence.low


class LibftCopy(PatternExtractor):
    kind, title = "libft_copy", "The libft is in the repository"
    pattern = re.compile(r"\bcopy\b.*\bsources\b.*\blibft\b")
