"""src/scraper/jobs/job.py and summary.py: the state machine of one download."""
from __future__ import annotations

import logging

import httpx
import pytest

from scraper.core.exceptions import ScraperError, SessionExpired
from scraper.core.models import Stats
from scraper.jobs.job import DownloadJob, NoDownload
from scraper.jobs.state import JobState
from scraper.jobs.summary import DownloadSummary
from tests.scraper.jobs.fakes import command_of, raising


def run(**kwargs) -> DownloadJob:
    job = DownloadJob("j1", command_of(**kwargs))
    job.run()
    return job


def test_a_new_job_is_running_and_has_said_nothing():
    job = DownloadJob("j1", command_of(lines=("never run",)))
    snapshot = job.snapshot()
    assert (snapshot.state, snapshot.id, snapshot.lines, snapshot.next, snapshot.summary) == (JobState.RUNNING, "j1", [], 0, None)
    assert job.running and not job.finished.is_set()


def test_a_command_that_ends_well_is_done_with_a_summary_even_of_nothing():
    job = run(lines=("a", "b"))
    snapshot = job.snapshot()
    assert snapshot.state is JobState.DONE and snapshot.lines == ["a", "b"] and snapshot.next == 2
    assert snapshot.summary == DownloadSummary(0, 0, 0, (), ()) and snapshot.summary.empty
    assert job.finished.is_set() and not job.running


def test_the_summary_is_what_the_stats_of_the_run_hold():
    stats = Stats()
    stats.counts.update(subject=3, artifact=5, existing=2)
    stats.failed.append("samples/x.pdf")
    stats.no_files.append("Y (y)")
    summary = DownloadSummary.of(stats)
    assert summary == DownloadSummary(3, 5, 2, ("samples/x.pdf",), ("Y (y)",)) and not summary.empty
    assert DownloadSummary(0, 0, 0, ("x",), ()).empty is False and DownloadSummary(0, 0, 1, (), ()).empty is False


def test_a_command_that_saw_the_stop_request_ends_cancelled():
    job = DownloadJob("j1", command_of(lines=("working",), downloaded=2, stops=True))
    assert job.cancel() is JobState.RUNNING                           # (the state now: it has not stopped yet)
    job.run()
    snapshot = job.snapshot()
    assert snapshot.state is JobState.CANCELLED and snapshot.summary.downloaded_subjects == 2


def test_a_stop_that_came_too_late_does_not_change_how_it_ended():
    job = DownloadJob("j1", command_of(lines=("working",), stops=False))
    job.cancel()
    job.run()
    assert job.state is JobState.DONE


def test_a_cancelled_job_with_nothing_done_has_no_summary():
    job = DownloadJob("j1", command_of(stops=True))
    job.cancel()
    job.run()
    assert job.snapshot().state is JobState.CANCELLED and job.snapshot().summary is None


@pytest.mark.parametrize("downloaded,failed,has_summary", [(0, (), False), (1, (), True), (0, ("x.pdf",), True)])
def test_a_failed_job_has_a_summary_only_when_some_work_was_done(downloaded, failed, has_summary):
    job = run(then=raising(ScraperError("it broke")), downloaded=downloaded, failed=failed)
    snapshot = job.snapshot()
    assert snapshot.state is JobState.FAILED and snapshot.lines == ["it broke"]
    assert (snapshot.summary is not None) == has_summary


def test_an_expired_session_fails_the_job_and_tells_what_to_do():
    job = run(lines=("[1/2] x",), then=raising(SessionExpired()))
    snapshot = job.snapshot()
    assert snapshot.state is JobState.FAILED
    assert snapshot.lines == ["[1/2] x", "The session expired. Run it again: it logs in again and skips what you already have.",
                              "The saved session stopped working: run `make samples-login` on your computer, then download again."]


def test_a_network_error_fails_the_job_with_a_plain_message():
    job = run(then=raising(httpx.ConnectError("name resolution failed\nsecond line")))
    assert job.snapshot().state is JobState.FAILED and job.snapshot().lines == ["Network error: name resolution failed"]


def test_an_unexpected_error_fails_the_job_instead_of_killing_the_thread_silently(caplog):
    with caplog.at_level(logging.ERROR):
        job = run(then=raising(ZeroDivisionError("division by zero")))
    assert job.snapshot().state is JobState.FAILED and job.snapshot().lines == ["Unexpected error: division by zero"]
    assert job.finished.is_set() and "the download failed" in caplog.text and "ZeroDivisionError" in caplog.text     # (and the traceback is kept)


def test_the_command_is_given_the_stop_flag_of_its_job():
    flags = []

    def make(reporter, cancelled):
        flags.append(cancelled)
        return command_of()(reporter, cancelled)

    job = DownloadJob("j1", make)
    assert flags[0]() is False
    job.cancel()
    assert flags[0]() is True


def test_lines_are_read_from_a_given_index():
    job = run(lines=("a", "b", "c"))
    assert job.snapshot(1).lines == ["b", "c"] and job.snapshot(1).next == 3 and job.snapshot(3).lines == []


def test_a_snapshot_never_says_it_is_over_without_all_the_lines():
    """The job ends right after its lines were read: the snapshot must say `running` (what it was), not `done` with lines missing."""
    job = DownloadJob("j1", command_of(lines=("a", "b")))
    real = job.log.since

    def lines_then_the_job_ends(start):
        seen = real(start)
        job.run()
        return seen

    job.log.since = lines_then_the_job_ends
    first = job.snapshot()
    assert first.state is JobState.RUNNING and first.lines == []
    second = job.snapshot(first.next)
    assert second.state is JobState.DONE and first.lines + second.lines == ["a", "b"]


def test_the_job_shown_before_the_first_one_is_idle_and_cannot_be_stopped():
    nobody = NoDownload()
    snapshot = nobody.snapshot(5)
    assert (snapshot.state, snapshot.id, snapshot.lines, snapshot.next, snapshot.summary) == (JobState.IDLE, "", [], 0, None)
    assert nobody.cancel() is JobState.IDLE and nobody.running is False
