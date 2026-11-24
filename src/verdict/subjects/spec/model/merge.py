from __future__ import annotations

from verdict.core.models import Rule


def merge_rules(rules: list[Rule]) -> list[Rule]:
    """Collapse identical rules (same id), remembering every place they came from."""
    merged: dict[str, Rule] = {}
    for rule in rules:
        existing = merged.get(rule.id)
        if existing is None:
            merged[rule.id] = rule.model_copy(deep=True)
        else:
            for src in rule.sources:
                if src not in existing.sources:
                    existing.sources.append(src)
    return list(merged.values())
