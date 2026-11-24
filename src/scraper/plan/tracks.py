"""Which project belongs to which track of the subject library, and under what name it is kept.

* common-core       data/common-core.txt
* rncp              data/rncp_21.json: every project of every option, plus the "suite" projects
* post-common-core  data/post-common-core.txt

The .txt files hold one project per line (slug, name or id; `#` starts a comment). RNCP wins over post-common-core when a project is
in both, and a project in a piscine or a series (its children) goes where its parent goes. There are no sub-folders per RNCP, but a series (a piscine, `cpp-module-NN`, `kfs-N`) has a folder of its own (see layout.py).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from scraper.plan.catalog import Catalog, Project
from scraper.plan.layout import LayoutPlanner
from scraper.plan.target import Target

__all__ = ["TRACKS", "Target", "Plan", "build_plan"]
TRACKS = ("common-core", "post-common-core", "rncp")        # the folders of samples/, as the app knows them
ORDER = ("common-core", "rncp", "post-common-core")         # who wins when a project is in two lists


@dataclass
class Plan:
    targets: list[Target] = field(default_factory=list)
    unresolved: dict[str, list[str]] = field(default_factory=dict)      # track -> what the list names but the catalog does not know

    def of(self, track: str) -> list[Target]:
        return [t for t in self.targets if t.track == track]


def read_list(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line]


def rncp_ids(path: Path, *, with_experience: bool = False) -> list[int]:
    """Every project id of the RNCP file, once, in the order it appears."""
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [i for title in data.get("rncp", []) for option in title.get("options", []) for i in option.get("projects", [])]
    ids += data.get("suite", {}).get("projects", [])
    if with_experience:
        ids += data.get("experience", {}).get("projects", [])
    return list(dict.fromkeys(ids))


def build_plan(catalog: Catalog, data_dir: Path, *, with_children: bool = True, with_experience: bool = False) -> Plan:
    wanted: dict[str, list[Project]] = {track: [] for track in TRACKS}
    unresolved: dict[str, list[str]] = {}

    def add(track: str, token: str, project: Project | None) -> None:
        if project is None:
            unresolved.setdefault(track, []).append(token)
        else:
            wanted[track].append(project)

    for token in read_list(data_dir / "common-core.txt"):
        add("common-core", token, catalog.resolve(token))
    for pid in rncp_ids(data_dir / "rncp_21.json", with_experience=with_experience):
        add("rncp", f"id {pid}", catalog.by_id.get(pid))
    for token in read_list(data_dir / "post-common-core.txt"):
        add("post-common-core", token, catalog.resolve(token))

    plan = Plan(unresolved=unresolved)
    seen_ids: set[int] = set()
    seen_stems: set[str] = set()

    def take(track: str, project: Project, parent: Project | None) -> None:
        target = Target(track, project, parent)
        if project.id in seen_ids or target.stem in seen_stems:
            return
        seen_ids.add(project.id)
        seen_stems.add(target.stem)
        plan.targets.append(target)

    for track in ORDER:
        for project in wanted[track]:
            take(track, project, None)
            if with_children:
                for child in project.children:
                    take(track, child, project)
    plan.targets.sort(key=lambda t: (TRACKS.index(t.track), t.stem))
    plan.targets = LayoutPlanner().place(plan.targets)
    return plan
