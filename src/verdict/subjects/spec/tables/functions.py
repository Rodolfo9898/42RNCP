from __future__ import annotations

import re
from dataclasses import dataclass, field

from verdict.core.models import Rule, Section, Source
from verdict.subjects.spec.files import expand_files, file_params
from verdict.subjects.spec.model import Line, make_rule
from verdict.subjects.spec.vocabulary import identifiers


@dataclass
class Allowed:
    """The external functions the function tables of one part allow, and where the first of them was read."""

    source: Source
    functions: list[str] = field(default_factory=list)


class FunctionTables:
    """Function-style subjects (get_next_line, libft) give one table per function. This collects, per part, the names to define and
    the external functions allowed, and sums them up in one rule each once every table has been read."""

    def __init__(self, lines: list[Line], pdf: str) -> None:
        self.lines, self.pdf = lines, pdf
        self.names: dict[Section, list[str]] = {"mandatory": [], "bonus": []}
        self.allowed: dict[Section, Allowed] = {}
        self.is_libft = False

    def add(self, fields: dict[str, str], section: Section, source: Source) -> list[Rule]:
        """Takes one table in; its own `required_files` rule, if it names files."""
        if fields.get("function_name"):
            self.names[section].append(fields["function_name"].strip())
        acc = self.allowed.setdefault(section, Allowed(source))
        for name in identifiers(fields.get("functions", "")):
            if name not in acc.functions:
                acc.functions.append(name)
        required, notes = expand_files(fields.get("files", ""))
        if not (required or notes):
            return []
        return [make_rule("required_files", "Required files", text=f"Files to submit: {fields.get('files', '')}", section=section,
                          params=file_params(required, notes), source=source)]

    def summary(self) -> list[Rule]:
        """One `allowed_functions` rule per part, then one `functions_defined` rule per part."""
        rules = [self._allowed_rule(section, acc) for section, acc in self.allowed.items() if acc.functions]
        if self.is_libft:
            self.names["mandatory"] = libft_part1(self.lines) + self.names["mandatory"]
        for section in ("mandatory", "bonus"):
            if self.names[section]:
                rules.append(self._defined_rule(section, self.names[section]))
        return rules

    @staticmethod
    def _allowed_rule(section: Section, acc: Allowed) -> Rule:
        return make_rule("allowed_functions", "Only authorized external functions",
                         text=f"External functions: {', '.join(acc.functions)}", section=section,
                         params={"functions": acc.functions, "libft": False, "math": False, "mlx": False, "own_allowed": False},
                         source=acc.source)

    def _defined_rule(self, section: Section, names: list[str]) -> Rule:
        return make_rule("functions_defined", "Required functions are defined", text=f"{len(names)} functions: {', '.join(names)}",
                         section=section, params={"names": names}, source=Source(pdf=self.pdf, page=1))


def libft_part1(lines: list[Line]) -> list[str]:
    """The functions of the first part of the libft subject, listed as bullets (the table only names the second part)."""
    names: list[str] = []
    inside = False
    for line in lines:
        if re.match(r"part 1\b", line.text, re.I):
            inside = True
        elif re.match(r"part 2\b", line.text, re.I):
            break
        elif inside:
            m = re.fullmatch(r"[•◦]\s*([a-z_0-9]+)", line.text)
            if m:
                names.append("ft_" + m.group(1))
    return names
