"""Which projects are a series, and what the folder of the series is called (Strategy pattern).

A rule looks at ONE project and says how it would be filed. The planner keeps a placement only when enough projects share its
group, except for the folder of a piscine, which always exists. Like `cpp-modules/` holding `cpp00` ... `cpp09` in the projects folder:
the PDFs of a series are in a folder of their own, and so are their artifacts.

To support a new kind of series, add a class here and list it in DEFAULT_RULES.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from scraper.plan.names import PREFIX
from scraper.plan.target import Target


@dataclass(frozen=True)
class Placement:
    rule: str        # name of the rule that proposed it
    group: str       # the folder, e.g. "cpp-module"
    always: bool = False   # kept even when it holds a single project

    @property
    def key(self) -> tuple[str, str]:
        """Placements with the same key belong to the same group."""
        return self.rule, self.group.casefold()


class GroupingRule(ABC):
    name: str

    @abstractmethod
    def match(self, target: Target, heads: set[int]) -> Placement | None:
        """`heads`: the ids of the projects that have children in the plan."""


class PiscineRule(GroupingRule):
    """The projects of a piscine or of a series that the intra lists inside one project (Django - 0, Day 00, ...) go in the folder of
    that project, and so does the project itself:  piscine-django/{piscine-django, django-0-initiation, ...}."""

    name = "piscine"

    def match(self, target: Target, heads: set[int]) -> Placement | None:
        if target.parent is not None:
            return Placement(self.name, target.parent.slug.removeprefix(PREFIX), always=True)
        if target.project.id in heads:
            return Placement(self.name, target.slug.removeprefix(PREFIX), always=True)
        return None


class HyphenNumberedRule(GroupingRule):
    """The suffix says it: a trailing `-N` (or `-x`) after a name.  cpp-module-03  ->  cpp-module / kfs-3 -> kfs."""

    name = "hyphen"
    PATTERN = re.compile(r"^(?P<stem>.*[^\s-])-(?P<num>\d+|x)$", re.I)

    def match(self, target: Target, heads: set[int]) -> Placement | None:
        m = self.PATTERN.match(target.slug.removeprefix(PREFIX))
        return Placement(self.name, m["stem"]) if m else None


# Priority order: the first rule whose group is big enough wins.
DEFAULT_RULES: tuple[GroupingRule, ...] = (PiscineRule(), HyphenNumberedRule())
