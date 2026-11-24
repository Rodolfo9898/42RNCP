"""The PDFs of a review travel to the terminal container (which cannot see the workspace) once, and again only when they differ."""

import hashlib

import pytest

from tests.verdict.api.support import prepared_session
from verdict.gateways.terminal import NullTerminal


def digests(harness, sid):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (harness.settings.workspace / sid / "subjects").glob("*.pdf")}


def test_the_pdfs_are_handed_to_the_terminal_once_and_again_only_when_they_differ(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs5")
    session = harness.store.get(sid)
    harness.norm.sync(session)
    terminal = harness.terminal
    harness.handover.push(session)
    assert [kind for kind, _ in terminal.calls] == ["subject_digests", "put_subjects"]
    assert sorted(terminal.held[sid]) == ["en.norm.pdf", "push_swap.pdf"]
    assert {name: hashlib.sha256(data).hexdigest() for name, data in terminal.held[sid].items()} == digests(harness, sid)
    terminal.calls.clear()
    harness.handover.push(session)
    assert [kind for kind, _ in terminal.calls] == ["subject_digests"]                 # it already has exactly these: nothing is sent
    terminal.held[sid]["extra.pdf"] = b"%PDF-1.4 a file it should not have"
    terminal.calls.clear()
    harness.handover.push(session)
    assert [kind for kind, _ in terminal.calls] == ["subject_digests", "put_subjects"]      # so the set is replaced
    assert sorted(terminal.held[sid]) == ["en.norm.pdf", "push_swap.pdf"]


def test_a_removed_subject_disappears_over_there(client):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs5b")
    harness.handover.push(harness.store.get(sid))
    assert sorted(harness.terminal.held[sid]) == ["en.norm.pdf", "push_swap.pdf"]
    c.delete(f"/api/sessions/{sid}/subjects/push_swap.pdf")                            # (main.c is C: the Norm stays)
    harness.handover.push(harness.store.get(sid))
    assert sorted(harness.terminal.held[sid]) == ["en.norm.pdf"]


def test_handing_over_the_pdfs_never_stops_a_terminal_from_opening(client, make_client, monkeypatch):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs6")
    harness.terminal.down = True
    harness.handover.push(harness.store.get(sid))                                      # unreachable: no exception
    assert harness.terminal.of("put_subjects") == [] and harness.terminal.held == {}
    other, other_harness = make_client(terminal=NullTerminal())
    other_sid, _ = prepared_session(other, other_harness, "pdfs6b")
    monkeypatch.setattr(other_harness.files, "sync", lambda session: pytest.fail("there is no terminal to give the files to"))
    other_harness.handover.push(other_harness.store.get(other_sid))                    # not configured: nothing is attempted


def test_a_terminal_that_refuses_the_files_is_logged_not_raised(client, caplog):
    c, harness = client
    sid, _ = prepared_session(c, harness, "pdfs6c")
    harness.terminal.down = True
    with caplog.at_level("WARNING", logger="verdict"):
        harness.handover.push(harness.store.get(sid))
    assert "could not hand the subject PDFs to the terminal" in caplog.text
