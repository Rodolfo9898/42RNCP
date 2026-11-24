"""The two questions a review puts to a backend: what is in the repository, and what about the items a script could not check."""

from __future__ import annotations

from verdict.core.models import AIComponent, AIOverview, AIReview, Improvement
from verdict.reviews.ai.analysis.citations import CitationVerifier
from verdict.reviews.ai.analysis.models import AnalysisOut, ImprovementOut, OverviewOut, ReviewItemOut, ReviewOut
from verdict.reviews.ai.analysis.tasks import SYSTEM, analysis_task, review_task
from verdict.reviews.ai.contract import Backend, Usage, clean
from verdict.reviews.digest import Digest


class Analyst:
    """Asks a backend the two questions (Facade over the backend, the digest and the checks on its answers).

    Advisory only: nothing here changes a check result or the verdict. Every text is cleaned and every cited
    file/line verified against the digest before it is used."""

    def __init__(self, backend: Backend, digest: Digest, usage: Usage):
        self.backend, self.digest, self.usage = backend, digest, usage
        self.citations = CitationVerifier(digest)

    def analyze(self, *, subjects: list[str], summary: str, known_titles: list[str]) -> tuple[AIOverview, list[Improvement]]:
        self.backend.job.notify("Step 1: describing the repository and looking for improvements")
        out: AnalysisOut = self.backend.structured(SYSTEM, self.digest.text, analysis_task(subjects, summary, known_titles), AnalysisOut, self.usage)
        improvements = [self._improvement(item) for item in out.improvements[:15]]
        return self._overview(out.overview), [i for i in improvements if i is not None]

    def review(self, items: list[tuple[str, str]], subjects: list[str] | None = None) -> dict[str, AIReview]:
        reviews: dict[str, AIReview] = {}
        for start in range(0, len(items), self.backend.batch):
            batch = items[start:start + self.backend.batch]
            wanted = {rule_id for rule_id, _ in batch}
            self.backend.job.notify(f"Step 2: assessing manual-review items {start + 1}–{start + len(batch)} of {len(items)}")
            out: ReviewOut = self.backend.structured(SYSTEM, self.digest.text, review_task(batch, subjects), ReviewOut, self.usage)
            for entry in out.items:
                if entry.rule_id in wanted and entry.rule_id not in reviews:
                    reviews[entry.rule_id] = self._assessment(entry)
            for rule_id in wanted - set(reviews):
                reviews[rule_id] = AIReview(rule_id=rule_id, assessment="unclear", finding="The model returned no assessment for this item.")
        return reviews

    @staticmethod
    def _overview(out: OverviewOut) -> AIOverview:
        return AIOverview(
            purpose=clean(out.purpose, 800),
            languages=[clean(x, 40) for x in out.languages[:8]],
            build_and_run=clean(out.build_and_run, 800),
            components=[AIComponent(path=clean(c.path, 200), role=clean(c.role, 300)) for c in out.components[:15]],
            notable=[clean(x, 400) for x in out.notable[:10]],
            not_found=[clean(x, 300) for x in out.not_found[:10]],
        )

    def _improvement(self, item: ImprovementOut) -> Improvement | None:
        evidence = self.citations.verified(item.evidence)
        if item.category in ("code", "logic") and not evidence:
            return None  # a claim about the code with nothing real to point at is not shown
        return Improvement(category=item.category, priority=item.priority, title=clean(item.title, 120),
                           detail=clean(item.detail, 600), evidence=evidence, source="ai")

    def _assessment(self, entry: ReviewItemOut) -> AIReview:
        return AIReview(rule_id=entry.rule_id, assessment=entry.assessment, why_manual=clean(entry.why_manual, 400),
                        finding=clean(entry.finding, 900), evidence=self.citations.verified(entry.evidence))


def analyze(backend: Backend, digest: Digest, *, subjects: list[str], summary: str, known_titles: list[str], usage: Usage) -> tuple[AIOverview, list[Improvement]]:
    return Analyst(backend, digest, usage).analyze(subjects=subjects, summary=summary, known_titles=known_titles)


def review(backend: Backend, digest: Digest, items: list[tuple[str, str]], usage: Usage, subjects: list[str] | None = None) -> dict[str, AIReview]:
    return Analyst(backend, digest, usage).review(items, subjects)
