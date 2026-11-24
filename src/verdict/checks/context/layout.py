"""Where the work of a rule is: which folder (unit) of the repository it applies to."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.constants import strict_layout
from verdict.checks.context.memo import memo
from verdict.core.models import Rule, Section


class Layout:
    """Maps the folders a subject names to the folders the project really has, and lists the rules' programs and units. Whether the
    layout of the subject is binding at all depends on the subjects the rules come from (see shared.constants.evaluation_rules)."""

    def __init__(self, repo: Path, rules: list[Rule], cache: dict[str, Any]) -> None:
        self.repo, self.rules, self.cache = repo, rules, cache

    @property
    def strict(self) -> bool:
        """libft, ft_printf and get_next_line: the files to turn in must be exactly as the subject says. Everywhere else the layout of
        the subject is not binding: the files must exist, wherever they sit (see shared.evaluation_rules)."""
        return memo(self.cache, "strict_layout", lambda: strict_layout(s.pdf for r in self.rules for s in r.sources))

    def unit_dir(self, unit: str) -> Path:
        path = (self.repo / unit).resolve()
        if unit in (".", "") or path.is_dir() or self.strict:
            return path
        return (self.repo / self.moved_unit(unit)).resolve()

    def moved_unit(self, unit: str) -> str:
        """Where the work of a program folder the subject names (philo_bonus/) is looked for when the project does not have that
        folder: a project may share its code between programs (DRY) instead of copying the subject's layout. Only for folders that
        hold a program; a missing exercise folder (C++ modules) is missing work. `unit` itself when there is nothing to move to."""
        moved = self.cache.setdefault("moved_units", {})
        if unit not in moved:
            moved[unit] = self._shared_folder(unit)
        return moved[unit]

    def _shared_folder(self, unit: str) -> str:
        if (self.repo / unit).is_dir() or not any(r.kind == "program" and r.unit == unit for r in self.rules):
            return unit
        others = [u for u in dict.fromkeys(r.unit for r in self.rules) if u not in (".", "", unit)
                  and (self.repo / u / "Makefile").is_file()]
        candidates = [u for u in others if unit.startswith(u)] + (["."] if (self.repo / "Makefile").is_file() else []) + others
        return candidates[0] if candidates else "."

    def units(self) -> list[str]:
        """The folders that are built, once each (two units can share a folder when the project shares its code)."""
        seen: dict[str, None] = {}
        for r in self.rules:
            if r.kind in ("build_unit", "program") or (r.kind == "required_files" and r.unit != "."):
                seen.setdefault(r.unit)
        out: list[str] = []
        folders: set[Path] = set()
        for unit in seen:
            folder = self.unit_dir(unit)
            if folder not in folders:
                folders.add(folder)
                out.append(unit)
        return out or ["."]

    def programs(self, unit: str, section: Section | None = None) -> list[str]:
        return [
            r.params["program"] for r in self.rules
            if r.kind == "program" and r.unit == unit and (section is None or r.section == section)
        ]

    def has_makefile(self, unit: str) -> bool:
        return (self.unit_dir(unit) / "Makefile").is_file()
