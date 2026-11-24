"""AiJobs: the running AI reviews, one per session, so that one can be told to stop."""

from verdict.ai_review.jobs import AiJobs
from verdict.reviews.ai import Job


def test_cancelling_tells_the_job_to_stop_and_forgets_it():
    jobs, job = AiJobs(), Job()
    jobs.add("s1", job)
    assert jobs.cancel("s1") is True and job.cancel.is_set()
    assert jobs.cancel("s1") is False                      # (it is no longer listed)


def test_cancelling_a_session_without_a_job_is_not_an_error():
    jobs = AiJobs()
    assert jobs.cancel("nobody") is False
    jobs.stop_listed("nobody")
    jobs.discard("nobody", Job())


def test_stopping_a_job_keeps_it_listed_until_its_own_thread_removes_it():
    jobs, job = AiJobs(), Job()
    jobs.add("s1", job)
    jobs.stop_listed("s1")
    assert job.cancel.is_set() and jobs.cancel("s1") is True      # still there to be found
    jobs.add("s1", job)
    jobs.discard("s1", job)
    assert jobs.cancel("s1") is False


def test_a_job_that_ends_never_removes_the_one_that_replaced_it():
    jobs, old, new = AiJobs(), Job(), Job()
    jobs.add("s1", old)
    jobs.add("s1", new)                                    # a second review was started for the session
    jobs.discard("s1", old)
    assert jobs.cancel("s1") is True and new.cancel.is_set() and not old.cancel.is_set()


def test_each_session_has_its_own_job():
    jobs, one, two = AiJobs(), Job(), Job()
    jobs.add("s1", one)
    jobs.add("s2", two)
    jobs.cancel("s1")
    assert one.cancel.is_set() and not two.cancel.is_set()
