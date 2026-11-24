from verdict.reviews.prompts import MAX_ITEMS
from tests.verdict.reviews.prompts.samples import build, r


def test_huge_subjects_are_capped():
    many = [r("manual", "Needs manual review", f"Requirement number {n} must hold. " + "x" * 600) for n in range(MAX_ITEMS + 30)]
    prompt, stats = build(many)
    assert stats["items"] == MAX_ITEMS and stats["chars"] == len(prompt)
    requirements = prompt.split("A. Requirements")[1].split("B. Limits")[0]            # (the instructions around them have long lines of their own)
    assert max(len(line) for line in requirements.splitlines()) < 700
