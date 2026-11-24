"""How a project is called on disk: `samples/<track>/<stem>.pdf` and `artifacts/<stem>/`.

The stem is the intra slug without its `42cursus-` prefix, except where the subjects already in `samples/` were named by hand
(`cpp00`, `kfs1`, `fractol`, ...): those names are kept, because the review reads some of them (`cpp00` gives the C++ module number;
`libft`, `ft_printf` and `get_next_line` switch on the strict layout).
"""
from __future__ import annotations

import re

from .utils import safe_name

PREFIX = "42cursus-"
ALIASES = {
    "fract-ol": "fractol",
    "music-room": "music_room",
    "snow-crash": "snow_crash",
    "ready-set-boole": "ready_set_boole",
    "expert-system": "expert-systems",
}
PATTERNS = [(re.compile(r"^cpp-module-(\d+)$"), r"cpp\1"), (re.compile(r"^kfs-(\w+)$"), r"kfs\1")]


def stem(slug: str) -> str:
    name = slug.strip().lower().removeprefix(PREFIX)
    for pattern, replacement in PATTERNS:
        if pattern.match(name):
            return pattern.sub(replacement, name)
    return safe_name(ALIASES.get(name, name))


def key(name: str) -> str:
    """What two spellings of the same project have in common (`kfs-1`, `kfs1`, `Kfs_1`): letters and digits, lower case."""
    return re.sub(r"[^a-z0-9]", "", name.lower())
