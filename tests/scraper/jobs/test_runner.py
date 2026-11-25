"""src/scraper/jobs/runner.py: one download at a time, in a thread of its own."""
from __future__ import annotations

import threading

import pytest

from scraper.jobs.job import DownloadJob
from scraper.jobs.runner import AlreadyRunning, DownloadRunner, in_a_thread, random_id
from scraper.jobs.state import JobState
from tests.scraper.jobs.fakes import command_of
from tests.scraper.support import Starter


def runner_with(starter: Starter) -> DownloadRunner:
    ids = iter(range(1, 100))
    return DownloadRunner(starter, new_id=lambda: f"job-{next(ids)}")


def test_before_the_first_download_there_is_an_idle_one_that_cannot_be_stopped():
    runner = runner_with(Starter())
    assert runner.running is False and runner.cancel() is JobState.IDLE
    snapshot = runner.snapshot()
    assert (snapshot.state, snapshot.id, snapshot.lines, snapshot.summary) == (JobState.IDLE, "", [], None)


def test_a_started_download_is_running_until_its_thread_has_run_it():
    starter = Starter()
    runner = runner_with(starter)
    job = runner.start(command_of(lines=("hello",)))
    assert isinstance(job, DownloadJob) and job.id == "job-1" and runner.running
    assert runner.snapshot().state is JobState.RUNNING and runner.snapshot().id == "job-1"
    starter.run()
    assert not runner.running and runner.snapshot().state is JobState.DONE and runner.snapshot().lines == ["hello"]


def test_a_second_download_is_refused_while_one_runs_and_allowed_when_it_is_over():
    starter = Starter()
    runner = runner_with(starter)
    runner.start(command_of())
    with pytest.raises(AlreadyRunning, match="already running"):
        runner.start(command_of())
    assert starter.started == 1 and runner.snapshot().id == "job-1"
    starter.run()
    assert runner.start(command_of()).id == "job-2"


def test_a_finished_download_stays_the_current_one_until_the_next_starts():
    starter = Starter()
    runner = runner_with(starter)
    runner.start(command_of(lines=("one", "two")))
    starter.run()
    assert runner.snapshot().lines == ["one", "two"] and runner.snapshot().id == "job-1"
    runner.start(command_of(lines=("other",)))
    assert runner.snapshot().id == "job-2" and runner.snapshot().lines == []


def test_a_job_that_cannot_be_built_leaves_the_runner_as_it_was():
    runner = runner_with(Starter())

    def broken(reporter, cancelled):
        raise RuntimeError("cannot build")

    with pytest.raises(RuntimeError):
        runner.start(broken)
    assert runner.running is False and runner.snapshot().state is JobState.IDLE
    assert runner.start(command_of()).id == "job-2"


def test_the_runner_stops_the_current_download_through_its_job():
    starter = Starter()
    runner = runner_with(starter)
    runner.start(command_of(stops=True, downloaded=1))
    assert runner.cancel() is JobState.RUNNING
    starter.run()
    assert runner.snapshot().state is JobState.CANCELLED and runner.cancel() is JobState.CANCELLED


def test_the_default_way_to_run_a_download_is_a_thread_of_its_own():
    runner = DownloadRunner(new_id=lambda: "job-1")
    make = command_of(lines=("from the thread",))
    job = runner.start(make)
    assert job.finished.wait(timeout=10)
    assert make.made.thread is not threading.current_thread() and make.made.thread.daemon and make.made.thread.name == "scraper-download"
    assert runner.snapshot().state is JobState.DONE and runner.snapshot().lines == ["from the thread"]


def test_a_stop_reaches_a_download_that_is_running_in_its_thread():
    runner = DownloadRunner(new_id=lambda: "job-1")
    make = command_of(stops=True, downloaded=1, hold=True)
    job = runner.start(make)
    command = make.made
    assert command.started.wait(timeout=10) and runner.running and runner.snapshot().state is JobState.RUNNING
    with pytest.raises(AlreadyRunning):
        runner.start(command_of())
    assert runner.cancel() is JobState.RUNNING
    command.release.set()
    assert job.finished.wait(timeout=10) and runner.snapshot().state is JobState.CANCELLED and not runner.running


def test_the_default_ids_are_unique_and_the_default_starter_returns_at_once():
    assert random_id() != random_id() and isinstance(random_id(), str) and random_id()
    done = threading.Event()
    in_a_thread(done.set)
    assert done.wait(timeout=10)
