"""Which checker answers which kind of rule."""

from __future__ import annotations

from collections.abc import Iterable

from verdict.checks.make.behavior import MakefileBehavior
from verdict.checks.make.compile import FlagsChecker, Std98Checker
from verdict.checks.make.makefile import BonusRuleChecker, MakefileRulesChecker
from verdict.checks.make.products import BuildUnitChecker, ProgramChecker
from verdict.checks.make.rebuild import NoRelinkChecker
from verdict.checks.engine.checker import Audit, Checker, Phase
from verdict.checks.engine.manual import ManualChecker
from verdict.checks.files.libft import LibftCopyChecker
from verdict.checks.files.required import RequiredFilesChecker
from verdict.checks.functions.allowed import AllowedFunctionsChecker
from verdict.checks.functions.defined import FunctionsDefinedChecker
from verdict.checks.norm.checkers import NoGlobalsChecker, NormChecker
from verdict.checks.repo.hygiene import RepoHygiene
from verdict.checks.repo.readme import ReadmeChecker
from verdict.checks.runtime.smoke import NoCrashChecker, NoLeaksChecker
from verdict.checks.source.cpp import CppForbiddenCallsChecker, CppForbiddenKeywordsChecker, CppNoStlChecker
from verdict.checks.source.language import IncludeGuardsChecker, LanguageChecker


class CheckerRegistry:
    """Registry of the checkers, by the kind of rule each one judges. A kind nobody handles gets the `fallback` (a Null Object: the
    rule is listed for a human). `opening` audits run before the rules, `closing` ones after them."""

    def __init__(self, checkers: Iterable[Checker], *, fallback: Checker, opening: Iterable[Audit] = (), closing: Iterable[Audit] = ()) -> None:
        self._by_kind = {checker.kind: checker for checker in checkers}
        self.fallback = fallback
        self.opening, self.closing = tuple(opening), tuple(closing)

    def for_kind(self, kind: str) -> Checker:
        return self._by_kind.get(kind, self.fallback)

    def phase_of(self, kind: str) -> Phase:
        return self.for_kind(kind).phase


def default_registry() -> CheckerRegistry:
    """Every checker of the review (Factory: a new registry each time, nothing is shared between reviews)."""
    manual = ManualChecker()
    return CheckerRegistry(
        [manual, RequiredFilesChecker(), LibftCopyChecker(), MakefileRulesChecker(), LanguageChecker(), IncludeGuardsChecker(),
         CppForbiddenCallsChecker(), CppForbiddenKeywordsChecker(), CppNoStlChecker(), BonusRuleChecker(), ReadmeChecker(),
         ProgramChecker(), BuildUnitChecker(), FlagsChecker(), Std98Checker(),
         NoRelinkChecker(), AllowedFunctionsChecker(), FunctionsDefinedChecker(), NormChecker(), NoGlobalsChecker(),
         NoCrashChecker(), NoLeaksChecker()],
        fallback=manual, opening=[RepoHygiene()], closing=[MakefileBehavior()],
    )
