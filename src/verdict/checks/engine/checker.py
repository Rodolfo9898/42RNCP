"""What a checker is: the base classes the rule kinds and the review-wide audits derive from."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from enum import IntEnum
from typing import Any

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.results import result
from verdict.core.models import CheckResult, Rule


class Phase(IntEnum):
    """The order the rules are checked in: what only reads files, then what builds, then what inspects the build, then what runs it."""

    STATIC = 0
    BUILD = 1
    ANALYSIS = 2
    RUNTIME = 3


class Checker:
    """Judges every rule of one `kind` (Template Method). `run` fixes the steps: `skip` answers early when the rule does not apply,
    `prepare` gathers the facts, `evaluate` turns them into results. A subclass only fills the steps it needs."""

    kind: str
    phase: Phase = Phase.STATIC

    def run(self, ctx: Ctx, rule: Rule) -> Iterator[CheckResult]:
        early = self.skip(ctx, rule)
        if early is not None:
            yield early
            return
        yield from self.evaluate(ctx, rule, self.prepare(ctx, rule))

    def skip(self, ctx: Ctx, rule: Rule) -> CheckResult | None:
        return None

    def prepare(self, ctx: Ctx, rule: Rule) -> Any:
        return None

    def evaluate(self, ctx: Ctx, rule: Rule, facts: Any) -> Iterable[CheckResult]:
        raise NotImplementedError

    def title(self, rule: Rule) -> str | None:
        """The title of this checker's results, when it is not the title of the rule."""
        return None

    def result(self, rule: Rule, status: str, detail: str = "", *, title: str | None = None, **more: Any) -> CheckResult:
        return result(rule, status, detail, title=title or self.title(rule), **more)


class Audit:
    """A check that belongs to no rule of the subject (repository hygiene, what the Makefile does): run once per review."""

    needs_sandbox = False

    def run(self, ctx: Ctx) -> Iterable[CheckResult]:
        raise NotImplementedError
