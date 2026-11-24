"""One place for "compute it once per review": the results live in the `cache` dict of the review's Ctx."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def memo(cache: dict[str, Any], key: str, compute: Callable[[], Any]) -> Any:
    if key not in cache:
        cache[key] = compute()
    return cache[key]
