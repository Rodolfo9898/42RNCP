from __future__ import annotations

import re
from typing import Any

from verdict.core.models import Rule, Section, Source
from verdict.subjects.spec.files import expand_files, file_params
from verdict.subjects.spec.model import make_rule
from verdict.subjects.spec.vocabulary import identifiers


class ProgramRules:
    """Turns one program table (Program Name, Files to Submit, Makefile, External Function, ...) into rules: the files, the Makefile
    rules, the program to build and the functions it may call, each from its own field."""

    def __init__(self, fields: dict[str, str], section: Section, source: Source) -> None:
        self.fields, self.section, self.source = fields, section, source
        self.unit, self.files = ".", fields.get("files", "")
        m = re.search(r"in (?:the )?director(?:y|ies)\s+([\w./-]+)", self.files, re.I)
        if m:
            self.unit = m.group(1).rstrip("/.,") or "."
            self.files = self.files[: m.start()]

    def rules(self) -> list[Rule]:
        return [*self._files(), *self._makefile(), *self._program(), *self._functions()]

    def _rule(self, kind: str, title: str, text: str, params: dict[str, Any]) -> Rule:
        return make_rule(kind, title, text=text, section=self.section, unit=self.unit, params=params, source=self.source)

    def _files(self) -> list[Rule]:
        required, notes = expand_files(self.files)
        text = f"Files to submit: {self.fields.get('files', '')}"
        if required:
            return [self._rule("required_files", "Required files", text, file_params(required, notes))]
        if notes:
            return [self._rule("manual", "Files to submit", text, {"text": self.files})]
        return []

    def _makefile(self) -> list[Rule]:
        mk = self.fields.get("makefile", "")
        targets = [t for t in re.findall(r"[\w$()]+", mk) if t]
        if not targets:
            return []
        targets = ["NAME" if t in ("$(NAME)", "NAME") else t for t in targets]
        return [self._rule("makefile_rules", "Makefile rules", f"Makefile: {mk}", {"targets": targets})]

    def _program(self) -> list[Rule]:
        program = self.fields.get("program", "").strip()
        if not program:
            return []
        return [self._rule("program", f"Builds `{program}`", f"Program name: {program}",
                           {"program": program, "bonus_target": self.section == "bonus"})]

    def _functions(self) -> list[Rule]:
        fn_text = self.fields.get("functions", "")
        if not fn_text or re.search(r"detailed below", fn_text, re.I):
            return []
        names = identifiers(re.sub(r"\([^)]*\)", lambda m: " " + m.group(0)[1:-1] + " ", fn_text))
        params: dict[str, Any] = {
            "functions": [n for n in names if n not in ("c",)],
            "libft": self.fields.get("libft", "").strip().lower().startswith("yes"),
            "math": bool(re.search(r"math library", fn_text, re.I)),
            "mlx": bool(re.search(r"minilibx", fn_text, re.I)),
            "own_allowed": bool(re.search(r"equivalent|YOU coded", fn_text, re.I)),
        }
        return [self._rule("allowed_functions", "Only authorized external functions", f"External functions: {fn_text}", params)]
