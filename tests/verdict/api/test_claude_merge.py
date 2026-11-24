"""claude's structured report becomes the one readable page: merged by the numbers of the prompt, overwriting what the scripts said."""

from tests.verdict.api.support import (block, prepared_session, put_claude, run_to_completion, session_with_claudes_report, structured_review)
from verdict.core.models import ClaudeVerdict


def session_with_merged_report(c, harness, name, data):
    """A session whose checks ran, with claude's report `data` merged. Returns the session id and the repository."""
    sid, repo = prepared_session(c, harness, name)
    run_to_completion(c, sid)
    c.get(f"/api/sessions/{sid}/prompts/review")
    harness.terminal.reports[sid] = block(data)
    assert put_claude(c, sid, force=True).status_code == 200
    return sid, repo


def a_failed_check(c, sid):
    return next(r for r in c.get(f"/api/sessions/{sid}").json()["results"] if r["status"] == "fail")


def test_the_prompt_stores_its_numbering_and_the_saved_report_is_merged_by_those_numbers(client):
    c, harness = client
    sid, repo = prepared_session(c, harness, "mg1")
    run_to_completion(c, sid)
    prompt = c.get(f"/api/sessions/{sid}/prompts/review").json()["text"]
    items = harness.store.get(sid).review_items
    assert items and [i.n for i in items] == list(range(1, len(items) + 1))
    assert all(f"{i.n}. {i.text}" in prompt for i in items)

    review = structured_review([i.n for i in items])
    harness.terminal.reports[sid] = review
    saved = put_claude(c, sid, force=True).json()
    assert saved["structured"] is True and saved["assessed"] == len(items) == saved["total"] and saved["problems"] == []

    document = (repo / "verdict.md").read_text()
    lacking = document[document.index("## ❌ Lacking"):document.index("## ⚠️ Second look")]
    second = document[document.index("## ⚠️ Second look"):document.index("## ✅ Ok")]
    assert "`Claude`" in lacking and "note for 1" in lacking and "_Check by hand:_ run it" in lacking and "`main.c:1`" in lacking
    assert "note for 2" in second and "it does compile with them" in second and "disagrees" not in document
    assert "Requirements claude found ok" in document
    assert "Long prose that stays in the session only." not in document                 # no second document stuffed into the first
    assert not (repo / "claude-review.md").exists() and "Claude's full report" not in document
    assert harness.store.get(sid).claude_review == review                                # the prose is kept in the session
    assert "⚠️ **PASS WITH ISSUES** · decided by Claude" in document and "> Mostly sound." in document
    improvements = document[document.index("## Improvements"):document.index("## Final verdict")]
    assert "Check the allocation" in improvements and "`main.c:2`" in improvements and "ghost.c" not in improvements   # invented file dropped
    assert "from claude's review" in improvements

    state = c.get(f"/api/sessions/{sid}").json()
    assert state["claude"]["structured"] and state["claude"]["verdict"]["decision"] == "pass with reservations"
    assert [i["title"] for i in state["improvements"]] == ["Check the allocation"]      # the app shows the same single list
    assert all(r["rule_id"] in state["ai"]["reviews"] for r in state["results"] if r["status"] == "manual")
    assert {v["by"] for v in state["ai"]["reviews"].values()} == {"Claude"}


def test_a_report_without_the_block_still_appears_but_is_flagged(client):
    c, harness = client
    sid, repo = prepared_session(c, harness, "mg2")
    run_to_completion(c, sid)
    c.get(f"/api/sessions/{sid}/prompts/review")
    harness.terminal.reports[sid] = "# Review\n\nJust prose, no data block.\n"
    saved = put_claude(c, sid, force=True).json()
    assert saved["structured"] is False and "no json block" in saved["problems"][0]
    document = (repo / "verdict.md").read_text()
    assert "## Claude's review (from the terminal)" in document and "Just prose, no data block." in document
    assert "could not be merged into the lists above" in document
    assert c.get(f"/api/sessions/{sid}").json()["claude"]["structured"] is False


def test_a_new_run_starts_from_nothing_claudes_answers_included(client):
    c, harness = client
    sid, repo = prepared_session(c, harness, "mg3")
    run_to_completion(c, sid)
    c.get(f"/api/sessions/{sid}/prompts/review")
    items = harness.store.get(sid).review_items
    harness.terminal.reports[sid] = structured_review([i.n for i in items])
    put_claude(c, sid, force=True)
    assert "Requirements claude found ok" in (repo / "verdict.md").read_text() and harness.store.get(sid).claude.structured
    again = run_to_completion(c, sid)                                                       # (its saved report is deleted by the run)
    assert again["ai"]["reviews"] == {} and again["claude"]["structured"] is False and again["claude"]["verdict"] is None
    assert "Requirements claude found ok" not in (repo / "verdict.md").read_text() and "decided by Claude" not in (repo / "verdict.md").read_text()
    session = harness.store.get(sid)
    assert session.claude_review == "" and not session.claude.structured and session.review_items == []


def test_the_whole_evaluation_reads_claudes_word_and_the_session_keeps_the_scripts(client):
    c, harness = client
    sid, repo = prepared_session(c, harness, "ow1")
    run_to_completion(c, sid)
    failed = a_failed_check(c, sid)
    c.get(f"/api/sessions/{sid}/prompts/review")
    harness.terminal.reports[sid] = block({"items": [], "verdict": {"decision": "ready to pass", "reason": "Good."},
                                           "corrections": [{"check": failed["title"], "status": "likely ok",
                                                            "actually": "Claude tested this and it holds."}]})
    assert put_claude(c, sid, force=True).status_code == 200

    state = c.get(f"/api/sessions/{sid}").json()
    shown = next(r for r in state["results"] if r["title"] == failed["title"])
    assert (shown["status"], shown["detail"], shown["by"]) == ("pass", "Claude tested this and it holds.", "Claude")
    assert state["summary"]["overall"] == "PASS" and state["summary"]["decided_by"] == "claude"
    document = (repo / "verdict.md").read_text()
    assert "Claude tested this and it holds." in document and "✅ **PASS** · decided by Claude" in document
    assert not failed["detail"] or failed["detail"] not in document
    kept = next(r for r in harness.store.get(sid).results if r.title == failed["title"])
    assert (kept.status, kept.detail, kept.by) == ("fail", failed["detail"], "script")
    assert failed["title"] not in c.get(f"/api/sessions/{sid}/prompts/fix").json()["text"].split("HOW TO WORK")[1]


def test_a_fix_report_updates_verdict_md_and_says_what_was_corrected(client):
    c, harness = client
    sid, repo = session_with_merged_report(c, harness, "ow2", {"items": [], "verdict": {"decision": "do not pass", "reason": "Broken."},
                                                               "improvements": [{"title": "Old idea", "category": "code"}]})
    assert "❌ **FAIL** · decided by Claude" in (repo / "verdict.md").read_text()
    harness.terminal.reports[sid] = block({
        "fixes": [{"issue": "The Makefile", "status": "fixed", "detail": "Added the rules; make re works.", "evidence": ["main.c:1"]}],
        "improvements": [{"title": "Old idea", "category": "code"}, {"title": "Brand new idea", "category": "logic"}],
        "verdict": {"decision": "ready to pass", "reason": "Fixed."}})
    assert put_claude(c, sid).json()["new"] is True                                         # (what the editor does after each pass)
    document = (repo / "verdict.md").read_text()
    assert "✅ **PASS** · decided by Claude" in document and "> Fixed." in document
    fixes = document[document.index("## 🛠 What Claude corrected (1)"):document.index("## ❌ Lacking")]
    assert "**The Makefile** — fixed: Added the rules; make re works." in fixes and "`main.c:1`" in fixes
    assert "**New improvements found (1):** Brand new idea" in fixes and "Brand new idea** 🆕" in document


def test_a_later_report_that_cannot_be_read_does_not_undo_the_merged_one(client):
    c, harness = client
    sid, repo = session_with_merged_report(c, harness, "ow3", {"items": [], "verdict": {"decision": "ready to pass", "reason": "Good."}})
    harness.terminal.reports[sid] = "# just prose, no block"
    put_claude(c, sid)
    state = c.get(f"/api/sessions/{sid}").json()
    assert state["summary"]["decided_by"] == "claude" and state["claude"]["structured"] is True
    document = (repo / "verdict.md").read_text()
    assert "decided by Claude" in document and "no json block" in document and "just prose" not in document


def test_a_run_ends_what_claude_said_its_corrections_and_what_it_fixed_included(client):
    c, harness = client
    sid, repo = prepared_session(c, harness, "ow4")
    run_to_completion(c, sid)
    failed = a_failed_check(c, sid)
    c.get(f"/api/sessions/{sid}/prompts/review")
    harness.terminal.reports[sid] = block({
        "items": [], "verdict": {"decision": "ready to pass", "reason": "Good."},
        "corrections": [{"check": failed["title"], "status": "likely ok", "actually": "Claude tested this and it holds."}],
        "fixes": [{"issue": "The Makefile", "status": "fixed", "detail": "Added the rules."}]})
    assert put_claude(c, sid, force=True).status_code == 200
    assert "What Claude corrected" in (repo / "verdict.md").read_text()

    state = run_to_completion(c, sid)
    assert state["summary"]["decided_by"] == "scripts" and state["summary"]["overall"] == "FAIL" and state["claude"]["fixes"] == []
    assert next(r for r in state["results"] if r["title"] == failed["title"])["by"] == "script"
    document = (repo / "verdict.md").read_text()
    assert "What Claude corrected" not in document and "decided by Claude" not in document and "Claude tested this" not in document


def test_after_the_merge_claudes_decision_is_the_result_in_the_app_and_in_verdict_md(client):
    c, harness = client
    sid, repo, _ = session_with_claudes_report(c, harness, "fs1")
    assert c.get(f"/api/sessions/{sid}").json()["summary"]["decided_by"] == "scripts"
    assert put_claude(c, sid, force=True).status_code == 200
    summary = c.get(f"/api/sessions/{sid}").json()["summary"]
    assert harness.store.get(sid).claude.verdict.decision == "pass with reservations"
    assert (summary["overall"], summary["decided_by"]) == ("PASS WITH ISSUES", "claude") and summary["lists"] == "FAIL"     # (item 1 is a problem, claude is more lenient)
    text = (repo / "verdict.md").read_text()
    assert "decided by Claude: **pass with reservations** (the lists below alone say FAIL)" in text and "**Result: PASS WITH ISSUES**" in text
    for decision, expected in (("ready to pass", "PASS"), ("do not pass", "FAIL")):
        harness.store.get(sid).claude.verdict = ClaudeVerdict(decision=decision, reason="x")
        assert c.get(f"/api/sessions/{sid}").json()["summary"]["overall"] == expected
        assert f"**Result: {expected}**" in c.get(f"/api/sessions/{sid}/verdict.md").text
