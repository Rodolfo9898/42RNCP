"""src/scraper/jobs/log.py: the log of a download, written by one thread and read by others."""
from __future__ import annotations

import threading

import pytest

from scraper.jobs.log import LogReporter


@pytest.mark.parametrize("message,lines", [("one line", ["one line"]), ("a\nb", ["a", "b"]), ("", [""]), ("\nafter a gap", ["", "after a gap"]),
                                           ("two\n", ["two", ""])])
def test_a_message_is_as_many_lines_as_print_would_have_made_of_it(message, lines):
    log = LogReporter()
    log.log(message)
    assert log.since(0) == (lines, len(lines))


def test_the_lines_come_from_where_the_reader_stopped():
    log = LogReporter()
    for n in range(5):
        log.log(f"line {n}")
    lines, following = log.since(0)
    assert lines == [f"line {n}" for n in range(5)] and following == 5
    log.log("more\nand more")
    assert log.since(following) == (["more", "and more"], 7)
    assert log.since(7) == ([], 7)
    assert log.since(99) == ([], 7)                                   # (a reader that is ahead gets nothing, and the real count)


def test_nothing_is_lost_when_several_threads_write_at_once():
    log, writers, each = LogReporter(), 8, 200
    start = threading.Barrier(writers)

    def write(who: int) -> None:
        start.wait()
        for n in range(each):
            log.log(f"{who}:{n}")

    threads = [threading.Thread(target=write, args=(who,)) for who in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    lines, following = log.since(0)
    assert following == writers * each == len(lines)
    for who in range(writers):                                        # each writer's own lines are in the order it wrote them
        assert [line for line in lines if line.startswith(f"{who}:")] == [f"{who}:{n}" for n in range(each)]
