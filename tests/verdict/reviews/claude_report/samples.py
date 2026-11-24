"""A review prompt's items, the files it was about, and a report that answers it."""

import json

from verdict.core.models import ReviewItem


FILES = {"ft_strchr.c": 30, "Makefile": 60, "main.c": 10}


ITEMS = [ReviewItem(n=1, text="strchr must work", rule_ids=["r1", "r1b"]), ReviewItem(n=2, text="no relink", rule_ids=["r2"]),
         ReviewItem(n=3, text="bonus files", rule_ids=["r3"])]


def report(data, prose="# My review\n\nSome prose.\n"):
    return f"{prose}\n```json\n{json.dumps(data)}\n```\n"


GOOD = {
    "items": [
        {"n": 1, "status": "likely a problem", "note": "Bytes above 0x7f are missed.", "check_by_hand": "Run on x86.", "evidence": ["ft_strchr.c:20,24"]},
        {"n": 2, "status": "unclear", "note": "bonus relinks.", "check_by_hand": "", "evidence": ["Makefile:23-25"]},
        {"n": 3, "status": "likely ok", "note": "Fine.", "evidence": []},
    ],
    "corrections": [{"check": "Makefile has a bonus rule", "status": "likely ok", "says": "no bonus files", "actually": "ft_lst*.c exist", "evidence": ["main.c:2", "ghost.c:1"]}],
    "improvements": [{"category": "code", "priority": "high", "title": "Fix strchr", "detail": "cast", "evidence": ["ft_strchr.c:20"]}],
    "verdict": {"decision": "do not pass", "reason": "README missing."},
}
