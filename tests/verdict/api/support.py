"""What the web-layer tests plug into the app and build with: a terminal that records what it is asked, a `spawn` that runs
background work where the test can see it, and the session builders every topic uses (the fixtures that use them are in conftest)."""

import hashlib
import json
from pathlib import Path

import httpx

from verdict.core.errors import Unavailable
from verdict.core.models import CheckResult
from verdict.sessions.store import RepoMeta

NORM = "en.norm.pdf"


class Spawner:
    """The `spawn` of the container for tests: the work starts at once, in the thread of the request, or is held until `release()`."""

    def __init__(self) -> None:
        self.holding, self.held = False, []

    def __call__(self, function, *args) -> None:
        if self.holding:
            self.held.append((function, args))
        else:
            function(*args)

    def hold(self) -> None:
        self.holding = True

    def release(self) -> None:
        self.holding = False
        while self.held:
            function, args = self.held.pop(0)
            function(*args)


def tools(**broken) -> list[dict]:
    names = ["C compiler (cc)", "C++ compiler (c++)", "make", "docker client", "docker compose", "docker daemon"]
    return [{"name": n, "ok": n not in broken, "required": True, "detail": "x" if n not in broken else "not found"} for n in names]


class FakeTerminal:
    """The terminal service as the web app sees it, scripted: the report claude saved for each session, the PDFs it holds, its tools.
    Every call is recorded in `calls`. `down` makes it unreachable the way the real gateway is (a `delete_report` never raises)."""

    configured = True

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.reports: dict[str, str] = {}              # session id -> the report claude saved
        self.held: dict[str, dict[str, bytes]] = {}    # session id -> the PDFs the terminal was given
        self.tools = tools()
        self.down = False

    def of(self, kind: str) -> list[tuple]:
        return [call for call in self.calls if call[0] == kind]

    def _reach(self) -> None:
        if self.down:
            raise httpx.ConnectError("connection refused")

    def report(self, session_id: str) -> dict:
        self.calls.append(("report", session_id))
        self._reach()
        text = self.reports.get(session_id, "")
        return {"found": bool(text), "text": text, "name": "claude-review.md"}

    def delete_report(self, session_id: str) -> bool:
        self.calls.append(("delete_report", session_id))
        return not self.down and self.reports.pop(session_id, None) is not None

    def subject_digests(self, session_id: str) -> dict[str, str]:
        self.calls.append(("subject_digests", session_id))
        self._reach()
        return {name: hashlib.sha256(data).hexdigest() for name, data in self.held.get(session_id, {}).items()}

    def put_subjects(self, session_id: str, files: dict[str, bytes]) -> None:
        self.calls.append(("put_subjects", session_id))
        self._reach()
        self.held[session_id] = dict(files)

    def environment(self, deep: bool = False) -> dict:
        self.calls.append(("environment", deep))
        if self.down:
            raise Unavailable("could not reach the terminal service (ConnectError)")
        return {"tools": self.tools}


class UpSandbox:
    """A sandbox that is up and runs nothing."""

    def healthy(self) -> bool:
        return True


# ---------------------------------------------------------------- sessions


def new_session(c) -> str:
    created = c.post("/api/sessions")
    assert created.status_code == 201
    return created.json()["id"]


def attach_repo(harness, sid: str, path: str = "42/ps") -> Path:
    """A project in the projects folder that the session is about (no git: the checks and the pull cope with that)."""
    repo = harness.settings.projects / path
    repo.mkdir(parents=True)
    harness.store.get(sid).repo = RepoMeta(url="git@example.com:a/b.git", name="ps", path=path, commit="abc1234", subject="init", author="me")
    return repo


def prepared_session(c, harness, path: str = "rv") -> tuple[str, Path]:
    """A session with the push_swap subject from the library and a tiny C project, the checks not run yet."""
    sid = new_session(c)
    added = c.post(f"/api/sessions/{sid}/subjects", json={"paths": ["common-core/push_swap.pdf"]})
    assert added.status_code == 200
    repo = attach_repo(harness, sid, path)
    (repo / "Makefile").write_text("all:\n")
    (repo / "main.c").write_text("int main(void)\n{\n\treturn (0);\n}\n")
    return sid, repo


def run_to_completion(c, sid: str) -> dict:
    assert c.post(f"/api/sessions/{sid}/runs").status_code == 202
    return c.get(f"/api/sessions/{sid}").json()


def manual_ids(state: dict) -> list[str]:
    """The checks the scripts left to a human, as the AI is asked about them."""
    return sorted({r["rule_id"] for r in state["results"] if r["status"] == "manual"})


def a_result() -> CheckResult:
    return CheckResult(rule_id="r1", title="A check", status="pass", section="mandatory")


def made_session(c, harness, *, status: str = "pass", name: str = "libft") -> tuple[str, object]:
    """A session that was checked (one result of the given status) without running anything."""
    sid = new_session(c)
    session = harness.store.get(sid)
    session.repo = RepoMeta(url="", commit="", name=name, path=name)
    session.results = [CheckResult(rule_id="r1", title="A check", status=status, section="mandatory")]
    return sid, session


# ---------------------------------------------------------------- claude's review


REVIEW = """# Review of push_swap

## Section A
1. Likely a problem: no check for duplicates (main.c:3). <img src=x onerror=alert(1)>

```c
if (a < b) { /* <b>literal</b> */ }
```

## Verdict
do not pass - duplicates are not rejected and the sort is never verified.
"""


def structured_review(item_ids) -> str:
    """What claude would save: prose, then the json block, answering the numbered requirements."""
    answers = []
    for n in item_ids:
        status = ["likely a problem", "unclear", "likely ok", "not applicable"][(n - 1) % 4]
        answers.append({"n": n, "status": status, "note": f"note for {n}", "check_by_hand": "run it" if n == 1 else "",
                        "evidence": ["main.c:1"] if n == 1 else []})
    data = {"items": answers,
            "corrections": [{"check": "Compiles with -Wall -Wextra -Werror", "status": "unclear", "says": "some message",
                             "actually": "it does compile with them"}],
            "improvements": [{"category": "logic", "priority": "high", "title": "Check the allocation", "detail": "malloc can fail",
                              "evidence": ["main.c:2", "ghost.c:9"]}],
            "verdict": {"decision": "pass with reservations", "reason": "Mostly sound."}}
    return "# My review\n\nLong prose that stays in the session only.\n\n```c\nint x;\n```\n\n```json\n" + json.dumps(data) + "\n```\n"


def block(data: dict) -> str:
    return "# Report\n\n```json\n" + json.dumps(data) + "\n```\n"


def put_claude(c, sid: str, *, force: bool = False):
    return c.put(f"/api/sessions/{sid}/claude-review", json={"force": force})


def session_with_claudes_report(c, harness, name: str) -> tuple[str, Path, str]:
    """A session whose checks ran, with the numbering of the review prompt stored, and a terminal that holds claude's report."""
    sid, repo = prepared_session(c, harness, name)
    run_to_completion(c, sid)
    assert c.get(f"/api/sessions/{sid}/prompts/review").status_code == 200           # (stores the numbers the report answers)
    report = structured_review([i.n for i in harness.store.get(sid).review_items])
    harness.terminal.reports[sid] = report
    return sid, repo, report


def reviewed_session(c, harness, path: str) -> tuple[str, Path]:
    """A session whose verdict already has claude's (unstructured) review merged in."""
    sid, repo = prepared_session(c, harness, path)
    run_to_completion(c, sid)
    harness.terminal.reports[sid] = REVIEW
    assert put_claude(c, sid, force=True).status_code == 200
    assert harness.store.get(sid).claude_review == REVIEW and "Claude's review" in (repo / "verdict.md").read_text()
    return sid, repo


def assert_no_review(c, harness, sid: str) -> None:
    session = harness.store.get(sid)
    assert session.claude_review == "" and not session.claude.structured and session.review_items == []
    assert not any(v.by == "Claude" for v in session.ai.reviews.values())
    assert c.get(f"/api/sessions/{sid}").json()["claude"]["verdict"] is None
