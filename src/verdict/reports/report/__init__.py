"""Aggregate check results into a verdict and render verdict.md.

verdict.md is ONE page that answers three questions, whoever found the answer (a script, or claude's review).
The facade of the sub-packages: summary (the result, claude's corrections), buckets (everything sorted into lacking / second look /
ok) and markdown (the document, a Builder with one renderer per section).
"""

from verdict.reports.report.buckets.entries import Buckets, Entry
from verdict.reports.report.buckets.sorting import Bucketer, bucket
from verdict.reports.report.markdown.builder import MarkdownBuilder, render_markdown
from verdict.reports.report.markdown.text import code, fenced, inline, sources, where
from verdict.reports.report.summary.corrections import Corrector, corrected
from verdict.reports.report.summary.result import CLAUDE_DECIDES, ORDER, summarize
from verdict.reports.report.summary.status import CORRECTED_STATUS, REVIEWED_STATUS, shown_status
