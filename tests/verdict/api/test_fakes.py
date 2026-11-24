"""The stand-ins of these tests must behave like what they replace, or the tests prove nothing."""

import hashlib

import httpx
import pytest

from tests.verdict.api.support import FakeTerminal, Spawner
from verdict.core.errors import Unavailable
from verdict.gateways.terminal import NullTerminal, TerminalGateway


def public(cls):
    return {name for name in dir(cls) if not name.startswith("_")}


def test_the_fake_terminal_offers_what_the_gateway_offers():
    assert public(TerminalGateway) - {"url", "token", "transport"} <= public(FakeTerminal)
    assert public(NullTerminal) <= public(FakeTerminal)


def test_the_fake_terminal_remembers_what_it_is_given_and_gives_back_what_it_holds():
    terminal = FakeTerminal()
    assert terminal.report("s1") == {"found": False, "text": "", "name": "claude-review.md"}
    terminal.reports["s1"] = "the report"
    assert terminal.report("s1")["found"] is True and terminal.report("s1")["text"] == "the report"
    terminal.put_subjects("s1", {"a.pdf": b"%PDF"})
    assert terminal.subject_digests("s1") == {"a.pdf": hashlib.sha256(b"%PDF").hexdigest()}
    assert terminal.delete_report("s1") is True and terminal.delete_report("s1") is False and terminal.report("s1")["found"] is False
    assert [call[0] for call in terminal.calls][:2] == ["report", "report"]


def test_a_fake_terminal_that_is_down_fails_like_the_gateway_does():
    terminal = FakeTerminal()
    terminal.down = True
    with pytest.raises(httpx.HTTPError):
        terminal.report("s1")
    with pytest.raises(httpx.HTTPError):
        terminal.subject_digests("s1")
    with pytest.raises(Unavailable):
        terminal.environment()
    assert terminal.delete_report("s1") is False                      # best effort, never raises


def test_the_spawner_runs_work_at_once_or_when_released():
    spawn, seen = Spawner(), []
    spawn(seen.append, 1)
    spawn.hold()
    spawn(seen.append, 2)
    assert seen == [1]
    spawn.release()
    spawn(seen.append, 3)
    assert seen == [1, 2, 3]
