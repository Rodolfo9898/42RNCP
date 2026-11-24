"""The lists of the document: what is lacking, what needs a second look, what is ok, and the bonus part."""

from __future__ import annotations

from verdict.reports.report.markdown.context import ReportContext, Section
from verdict.reports.report.markdown.entries import entry_lines, section


class LackingSection(Section):
    def render(self, ctx: ReportContext) -> list[str]:
        out = ["## ❌ Lacking — fix these", ""]
        if not ctx.mandatory.lacking:
            return out + ["Nothing is lacking according to the checks" + (" and claude's review." if ctx.merged else "."), ""]
        for e in ctx.mandatory.lacking:
            out += entry_lines(e)
        return out + [""]


class SecondLookSection(Section):
    def render(self, ctx: ReportContext) -> list[str]:
        mandatory = ctx.mandatory
        out = ["## ⚠️ Second look — a human should verify these", ""]
        if not mandatory.second:
            return out + ["Nothing needs a second look.", ""]
        warnings = [e for e in mandatory.second if not e.requirement and e.by == "script"]
        judged = [e for e in mandatory.second if (e.requirement or e.by != "script") and e not in mandatory.unreviewed]
        out += section("Claude is unsure", judged) if ctx.merged else section("Unclear", judged)
        out += section("Warnings and checks that could not run", warnings)
        out += section("Not reviewed yet — a human has to judge these", mandatory.unreviewed,
                       "Run **✨ AI review** to have claude assess them." if not ctx.merged else "", compact=True)
        return out


class OkSection(Section):
    def render(self, ctx: ReportContext) -> list[str]:
        mandatory = ctx.mandatory
        checks_ok = [e for e in mandatory.ok if not e.requirement]
        reviewed_ok = [e for e in mandatory.ok if e.requirement]
        out = ["## ✅ Ok", ""]
        out += section("Checks that passed", checks_ok, compact=True)
        out += section("Requirements claude found ok", reviewed_ok, compact=True)
        out += section("Not applicable to this project", mandatory.not_applicable, compact=True)
        if not (checks_ok or reviewed_ok or mandatory.not_applicable):
            out += ["Nothing passed yet.", ""]
        return out


class BonusSection(Section):
    def render(self, ctx: ReportContext) -> list[str]:
        bonus = ctx.bonus
        if not any((bonus.lacking, bonus.second, bonus.ok, bonus.not_applicable, bonus.not_submitted)):
            return []
        out = ["## Bonus part", ""]
        out += section("Lacking", bonus.lacking) + section("Second look", bonus.second) + section("Ok", bonus.ok + bonus.not_applicable, compact=True)
        return out + section("Not submitted", bonus.not_submitted, compact=True)
