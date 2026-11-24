"""The 42cursus projects as the intra lists them (data/projects_21.json): id, name, slug and, for a piscine or a series, its children.

The slug is what the intra's project page is addressed by. The file is a snapshot (copied from the 42tools data): a project that is
newer than it can be added by slug in data/post-common-core.txt and is looked up by its page anyway.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from scraper.plan.names import PREFIX, key


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    slug: str
    children: tuple[Project, ...] = ()


class Catalog:
    def __init__(self, projects: list[Project]) -> None:
        self.projects = projects
        self.by_id = {p.id: p for p in projects}
        self.by_slug = {p.slug.lower(): p for p in projects}
        self._by_name: dict[str, list[Project]] = {}
        for p in projects:
            self._by_name.setdefault(key(p.name), []).append(p)

    @classmethod
    def load(cls, path: Path) -> Catalog:
        raw = json.loads(path.read_text(encoding="utf-8"))["projects"]
        entries = {entry["id"]: entry for entry in raw}
        projects = []
        for entry in raw:
            kids = []
            for child in entry.get("children") or []:
                full = {**entries.get(child.get("id"), {}), **child}       # a child is sometimes only an id: its own entry has the rest
                if full.get("slug") and full.get("name"):
                    kids.append(Project(full["id"], " ".join(full["name"].split()), full["slug"]))
            projects.append(Project(entry["id"], " ".join(entry["name"].split()), entry["slug"], tuple(kids)))
        return cls(projects)

    def resolve(self, token: str) -> Project | None:
        """A project by slug, slug without `42cursus-`, id, exact name, or - when only one project fits - spelling-insensitive name."""
        token = token.strip()
        low = token.lower()
        for found in (self.by_slug.get(low), self.by_slug.get(PREFIX + low), self.by_id.get(int(token)) if token.isdigit() else None):
            if found:
                return found
        exact = [p for p in self.projects if p.name.lower() == low]
        if exact:
            return exact[0]
        loose = self._by_name.get(key(token), [])
        return loose[0] if len(loose) == 1 else None
