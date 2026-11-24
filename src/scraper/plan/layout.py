"""Decides the folder of every project of the plan, given all of them."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace

from scraper.plan.groups import DEFAULT_RULES, GroupingRule, Placement
from scraper.plan.target import Target

# Nicer names for the folders the rules produce, in the spelling of the projects folder (cpp-modules/cpp00, ...).
GROUP_RENAMES: Mapping[str, str] = {"cpp-module": "cpp-modules"}


class LayoutPlanner:
    """Folds series into one folder instead of one long flat list:

      cpp-module-00 ... cpp-module-09                 -> cpp-modules/cpp00.pdf ... cpp09.pdf
      kfs-1 ... kfs-9, kfs-x                          -> kfs/kfs1.pdf ... kfsx.pdf
      Django - 0 - Initiation (child of Piscine Django) -> piscine-django/django-0-initiation.pdf, and the piscine's own PDF too

    A numbered series needs at least `min_group` members in its track, so a lone `little-penguin-1` stays on its own. The PDF keeps
    its full name wherever it is, and the artifacts of a project follow it: artifacts/<group>/<name>/.
    """

    def __init__(self, rules: Sequence[GroupingRule] = DEFAULT_RULES, renames: Mapping[str, str] = GROUP_RENAMES,
                 min_group: int = 2) -> None:
        self.rules, self.renames, self.min_group = tuple(rules), dict(renames), min_group

    def place(self, targets: Sequence[Target]) -> list[Target]:
        """The same targets, in the same order, each with the folder of its series (or none)."""
        placed: dict[tuple[str, str], Target] = {}
        for track in dict.fromkeys(t.track for t in targets):
            for t in self._place_track([t for t in targets if t.track == track]):
                placed[(t.track, t.stem)] = t
        return [placed[(t.track, t.stem)] for t in targets]

    def _place_track(self, mine: Sequence[Target]) -> list[Target]:
        heads = {t.parent.id for t in mine if t.parent is not None}
        candidates = {t.stem: [p for rule in self.rules if (p := rule.match(t, heads))] for t in mine}
        size = Counter(p.key for placements in candidates.values() for p in placements)
        shown: dict[tuple[str, str], str] = {}
        for placements in candidates.values():
            for p in placements:
                shown.setdefault(p.key, p.group)
        folders = {t.stem: self._choose(candidates[t.stem], size, shown) for t in mine}
        alone = {t.stem.casefold() for t in mine if not folders[t.stem]}
        return [replace(t, group=self._clear_of(folders[t.stem], alone)) for t in mine]

    def _choose(self, placements: list[Placement], size: Counter, shown: dict) -> str:
        for p in placements:
            if p.always or size[p.key] >= self.min_group:
                group = shown[p.key]
                return self.renames.get(group, group)
        return ""

    @staticmethod
    def _clear_of(group: str, alone: set[str]) -> str:
        """A folder must not share its name with a project that has none (cpp-modules next to a plain cpp-modules.pdf)."""
        return f"{group}-series" if group and group.casefold() in alone else group
