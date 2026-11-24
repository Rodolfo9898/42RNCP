"""verdict.md: ONE page that answers three questions, whoever found the answer (a script, or claude's review):

  ❌ what is lacking       -> fix these
  ⚠  what needs a second look -> a human should verify these
  ✅ what is ok            -> nothing to do

Only the structured answers of claude's report are merged here; its prose is kept in the session, not in the repository.
"""

from __future__ import annotations

from collections.abc import Sequence

from verdict.core.models import AIState, CheckResult, ClaudeReport, Improvement
from verdict.reports.report.markdown.ai import AiOverviewSection, ImprovementsSection
from verdict.reports.report.markdown.claude import ClaudeProseSection, FixesSection
from verdict.reports.report.markdown.context import ReportContext, Section
from verdict.reports.report.markdown.final import FinalVerdictSection
from verdict.reports.report.markdown.header import AtAGlanceSection, HeadlineSection, ProvenanceSection
from verdict.reports.report.markdown.lists import BonusSection, LackingSection, OkSection, SecondLookSection


class MarkdownBuilder:
    """Builder: the document is put together one section at a time, each written by its own renderer. The head always comes;
    the rest only once the checks have run."""

    def __init__(self, head: Sequence[Section], body: Sequence[Section]) -> None:
        self.head, self.body = list(head), list(body)

    @classmethod
    def standard(cls) -> MarkdownBuilder:
        return cls([HeadlineSection(), ProvenanceSection()],
                   [AtAGlanceSection(), FixesSection(), LackingSection(), SecondLookSection(), OkSection(), BonusSection(),
                    AiOverviewSection(), ImprovementsSection(), ClaudeProseSection(), FinalVerdictSection()])

    def build(self, ctx: ReportContext) -> str:
        out: list[str] = []
        for section in self.head + (self.body if ctx.results else []):
            out += section.render(ctx)
        return "\n".join(out).rstrip() + "\n"


def render_markdown(*, repo: dict | None, subjects: list[str], results: list[CheckResult],
                    improvements: list[Improvement] | None = None, readme: dict | None = None,
                    ai: AIState | None = None, claude_review: str = "", claude: ClaudeReport | None = None,
                    project: str = "") -> str:
    ctx = ReportContext.of(repo=repo, subjects=subjects, results=results, improvements=improvements, readme=readme, ai=ai,
                           claude_review=claude_review, claude=claude, project=project)
    return MarkdownBuilder.standard().build(ctx)
