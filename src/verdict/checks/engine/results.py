"""The pieces every checker builds its answers from."""

from __future__ import annotations

from verdict.core.models import CheckResult, Evidence, Rule


def result(rule: Rule | None, status: str, detail: str = "", *, title: str | None = None,
           evidence: list[Evidence] | None = None, log: str = "", auto: bool = True) -> CheckResult:
    return CheckResult(
        rule_id=rule.id if rule else None,
        title=title or (rule.title if rule else "Check"),
        status=status,  # type: ignore[arg-type]
        detail=detail,
        section=rule.section if rule else "mandatory",
        sources=rule.sources if rule else [],
        evidence=evidence or [],
        log=log[-6000:],
        auto=auto,
    )


def label(rule: Rule, text: str | None = None) -> str:
    base = text or rule.title
    return base if rule.unit == "." else f"{rule.unit}: {base}"


def tail(text: str, lines: int = 25) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])
