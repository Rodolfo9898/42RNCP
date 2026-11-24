"""The symbol a verdict result stands for in Progress.md."""

from __future__ import annotations

SYMBOLS = {"PASS": "✅", "PASS WITH ISSUES": "⚠️", "FAIL": "❌"}
NOT_RUN = "⬜"


class ProgressError(ValueError):
    pass


def symbol_for(result: str) -> str:
    """The symbol of a verdict result. Only a real result has one: a project that was not run is not marked."""
    try:
        return SYMBOLS[result]
    except KeyError:
        raise ProgressError(f"there is no result to record yet (it says {result or 'nothing'}): run the checks first") from None
