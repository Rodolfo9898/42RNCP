"""ScrapeCommand's two hooks for the downloader service: `cancelled` (asked between two projects) and `stats` (what the run did)."""
from __future__ import annotations

from scraper.cli.commands import ScrapeCommand, never_cancelled
from scraper.core.debug import NullDumper
from scraper.site.login import SessionManager
from scraper.storage.library import Library
from tests.scraper.test_scraper import Buffer, FakeAuthenticator, FakeSite, settings, target


def command(tmp_path, site, targets, **kwargs) -> tuple[ScrapeCommand, Buffer]:
    s, reporter = settings(tmp_path), Buffer()
    session = SessionManager(s, FakeAuthenticator(site), reporter, site.http)
    return ScrapeCommand(targets=targets, settings=s, session=session, library=Library(s.samples_dir, s.artifacts_dir), reporter=reporter,
                         dumper=NullDumper(), **kwargs), reporter


def three_projects() -> tuple[FakeSite, list]:
    site = FakeSite()
    slugs = ("one", "two", "three")
    for slug in slugs:
        site.add_project(slug, slug)
    return site, [target("rncp", slug, pid) for pid, slug in enumerate(slugs, 1)]


def test_by_default_nothing_asks_to_stop_and_the_stats_say_what_was_done(tmp_path):
    site, targets = three_projects()
    run, reporter = command(tmp_path, site, targets)
    assert run.cancelled is never_cancelled and never_cancelled() is False and run.stopped is False
    run.execute()
    assert run.stopped is False and run.stats.counts["subject"] == 3 and run.stats.failed == [] and "Done: 3 subject(s)" in reporter.text


def test_it_stops_between_two_projects_when_asked_and_keeps_what_was_done(tmp_path):
    site, targets = three_projects()
    asked = []

    def stop_after_the_first():
        asked.append(1)
        return len(asked) > 1

    run, reporter = command(tmp_path, site, targets, cancelled=stop_after_the_first)
    run.execute()
    assert run.stopped is True and len(asked) == 2
    assert reporter.lines[-1] == "Stopped on request." and "Done:" not in reporter.text and "[2/3]" not in reporter.text
    assert (tmp_path / "samples/rncp/one.pdf").is_file() and not (tmp_path / "samples/rncp/two.pdf").exists()
    assert run.stats.counts["subject"] == 1
    assert run.library.checked() == {"one"}                           # (so a later run starts from the second)


def test_a_stop_asked_before_the_first_project_does_nothing_at_all(tmp_path):
    site, targets = three_projects()
    run, reporter = command(tmp_path, site, targets, cancelled=lambda: True)
    run.execute()
    assert run.stopped and not (tmp_path / "samples").exists() and not run.stats.counts and reporter.lines[-1] == "Stopped on request."


def test_the_stop_is_not_asked_when_there_is_nothing_to_visit(tmp_path):
    site, targets = three_projects()
    run, _ = command(tmp_path, site, targets)
    run.execute()
    again, reporter = command(tmp_path, site, targets, cancelled=lambda: True)
    again.execute()
    assert again.stopped is False and "Nothing to do" in reporter.text
