from __future__ import annotations

import hashlib
import json
from typing import Any

from verdict.core.models import Rule, Section, Source


def make_rule(kind: str, title: str, *, text: str = "", section: Section = "mandatory",
              unit: str = ".", params: dict[str, Any] | None = None,
              source: Source | None = None) -> Rule:
    """Factory of the rules every extractor produces: the id is a hash of what the rule asks, so the same requirement found in two
    places (or two subjects) gets the same id and can be merged."""
    params = params or {}
    digest = hashlib.sha1(json.dumps([kind, unit, section, params], sort_keys=True).encode()).hexdigest()[:8]
    return Rule(
        id=f"{kind}:{digest}", kind=kind, title=title, text=text, section=section,
        unit=unit, params=params, sources=[source] if source else [],
    )
