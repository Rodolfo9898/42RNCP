"""The README of a project: whether it has one, and whether its subject dictates it."""

from __future__ import annotations

from verdict.checks import Ctx


def readme_status(ctx: Ctx) -> dict:
    root = [p for p in ctx.files() if len(p.parts) == 1]
    found = next((p for p in root if p.name == "README.md"), None) or next((p for p in root if p.name.lower().startswith("readme")), None)
    if not found:
        return {"present": False, "name": None, "lines": 0}
    return {"present": True, "name": found.name, "lines": len([l for l in ctx.read(found).splitlines() if l.strip()])}


def readme_required(ctx: Ctx) -> bool:
    """Common-core subjects dictate the README's content; later projects leave it free."""
    return any(r.kind == "readme" for r in ctx.rules)
