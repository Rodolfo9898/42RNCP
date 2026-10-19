from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai as ai_mod
from . import highlight as highlight_mod
from . import improve as improve_mod
from . import repo as repo_mod
from .digest import Digest, build_digest, line_index
from .claude_report import parse_report
from .prompts import build_review_prompt, manual_items
from .checks import VERDICT_MARKER, Ctx, run_checks
from .models import CheckResult
from .pdfread import read_pages
from .report import render_markdown, summarize
from .sandbox import Sandbox
from .spec import parse_subject
from .models import AIEvent, AIState
from .store import RepoMeta, Session, Store, Subject, safe_filename

WORKSPACE = Path(os.environ.get("WORKSPACE", "workspace")).resolve()
PROJECTS = Path(os.environ.get("PROJECTS_DIR", WORKSPACE / "projects")).resolve()
PROJECTS.mkdir(parents=True, exist_ok=True)
SAMPLES = Path(os.environ.get("SAMPLES_DIR", "/samples" if Path("/samples").is_dir() else "samples")).resolve()
MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_SUBJECTS = 20

app = FastAPI(title="verdict")
store = Store(WORKSPACE)
sandbox = Sandbox.from_env()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        # Scripts only from this origin. Styles may be inline (the viewer positions highlights, xterm.js sizes itself);
        # a style cannot run code. WebSockets are needed by the terminal tab.
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; "
        "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def session_or_404(session_id: str) -> Session:
    try:
        return store.get(session_id)
    except KeyError:
        raise HTTPException(404, "unknown session") from None


def repo_dir(session: Session) -> Path | None:
    """Where this session's clone lives (always inside the projects folder)."""
    if not session.repo or not session.repo.path:
        return None
    try:
        return repo_mod.safe_path(PROJECTS, session.repo.path)
    except repo_mod.RepoError:
        return None


def chosen_improvements(session: Session) -> list:
    """claude's own improvements replace the script heuristics once its report has been merged (one list, no duplicates)."""
    return session.claude.improvements if session.claude.structured and session.claude.improvements else session.improvements


def view(session: Session) -> dict:
    return {
        "id": session.id,
        "state": session.state,
        "message": session.message,
        "repo": session.repo.model_dump() if session.repo else None,
        "subjects": [
            {"name": s.name, "lang": s.lang, "pages": s.pages, "rules": [r.model_dump() for r in s.rules]}
            for s in session.subjects.values()
        ],
        "results": [r.model_dump() for r in session.results],
        "improvements": [i.model_dump() for i in chosen_improvements(session)],
        "claude": session.claude.model_dump(),
        "readme": session.readme,
        "verdict_file": session.verdict_file,
        "claude_review_at": session.claude_review_at,
        "claude_review_file": session.claude_review_file,
        "ai": session.ai.model_dump(),
        "summary": summarize(session.results),
    }


# ------------------------------------------------------------------ environment


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "sandbox": bool(sandbox and sandbox.healthy()),
            "llm": {"configured": ai_mod.configured(), "model": ai_mod.model_name(), "provider": ai_mod.provider(), "host": ai_mod.endpoint_host()}}


@app.get("/api/library")
def library() -> list[dict]:
    """Subject PDFs bundled with the deployment (the ./samples folder)."""
    if not SAMPLES.is_dir():
        return []
    return [{"name": p.name, "size": p.stat().st_size} for p in sorted(SAMPLES.glob("*.pdf"))]


# ------------------------------------------------------------------ sessions


@app.post("/api/sessions")
def create_session() -> dict:
    return view(store.create())


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = session_or_404(session_id)
    ensure_review_files(session)      # a stored review whose file is missing from the clone is written out
    return view(session)


def _add_subject(session: Session, name: str, data: bytes) -> None:
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, f"{name} is not a PDF")
    if len(session.subjects) >= MAX_SUBJECTS and name not in session.subjects:
        raise HTTPException(400, f"at most {MAX_SUBJECTS} subjects per session")
    try:
        pages = read_pages(data)
    except Exception as exc:
        raise HTTPException(400, f"could not read {name}: {exc}") from exc
    spec = parse_subject(name, pages)
    session.subjects[name] = Subject(name=name, lang=spec.lang, pages=len(pages), rules=spec.rules)
    session.results = []
    session.state = "idle"


@app.post("/api/sessions/{session_id}/subjects")
async def upload_subjects(session_id: str, files: list[UploadFile] = File(...)) -> dict:
    session = session_or_404(session_id)
    for upload in files:
        data = await upload.read(MAX_PDF_BYTES + 1)
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(413, f"{upload.filename} is larger than {MAX_PDF_BYTES // 2**20} MB")
        _add_subject(session, safe_filename(upload.filename or "subject.pdf"), data)
    store.save(session)
    return view(session)


class LibraryPick(BaseModel):
    names: list[str]


@app.post("/api/sessions/{session_id}/subjects/library")
def add_from_library(session_id: str, pick: LibraryPick) -> dict:
    session = session_or_404(session_id)
    available = {p.name: p for p in SAMPLES.glob("*.pdf")} if SAMPLES.is_dir() else {}
    for name in pick.names:
        if name not in available:
            raise HTTPException(404, f"{name} is not in the library")
        _add_subject(session, name, available[name].read_bytes())
    store.save(session)
    return view(session)


@app.delete("/api/sessions/{session_id}/subjects/{name}")
def remove_subject(session_id: str, name: str) -> dict:
    session = session_or_404(session_id)
    session.subjects.pop(name, None)
    session.results = []
    store.save(session)
    return view(session)


class RepoRequest(BaseModel):
    url: str
    name: str = ""
    destination: str = ""


@app.get("/api/ssh")
def ssh() -> dict:
    return repo_mod.ssh_status()


@app.get("/api/projects")
def projects() -> dict:
    """The projects folder and the sub-folders a clone can be placed in."""
    return {"root": PROJECTS.name, "folders": repo_mod.list_folders(PROJECTS)}


@app.post("/api/sessions/{session_id}/repo")
def clone_repo(session_id: str, req: RepoRequest) -> dict:
    session = session_or_404(session_id)
    if session.state in ("cloning", "running"):
        raise HTTPException(409, f"session is busy ({session.state})")
    try:
        url = repo_mod.validate_url(req.url)
        name = req.name.strip() or repo_mod.default_name(url)
        dest = repo_mod.resolve_destination(PROJECTS, req.destination, name)
    except repo_mod.RepoError as exc:
        raise HTTPException(400, str(exc)) from exc
    session.state, session.message = "cloning", ""
    try:
        info = repo_mod.clone(url, dest, WORKSPACE / "known_hosts")
    except repo_mod.RepoError as exc:
        session.state, session.message = "error", str(exc)
        store.save(session)
        raise HTTPException(400, str(exc)) from exc
    session.repo = RepoMeta(**info.__dict__, name=name, path=dest.relative_to(PROJECTS).as_posix())
    session.results, session.state = [], "idle"
    store.save(session)
    return view(session)


@app.get("/api/sessions/{session_id}/tree")
def repo_tree(session_id: str) -> list[dict]:
    root = repo_dir(session_or_404(session_id))
    return repo_mod.tree(root) if root and root.is_dir() else []


_highlight_cache: dict = {}


@app.get("/api/sessions/{session_id}/file")
def repo_file(session_id: str, path: str) -> dict:
    root = repo_dir(session_or_404(session_id))
    if root is None:
        raise HTTPException(404, "no repository cloned")
    try:
        file = repo_mod.read_text(root, path)
        if not file["binary"] and not file.get("truncated"):
            stat = repo_mod.safe_path(root, path).stat()
            key = (str(root), path, stat.st_size, stat.st_mtime_ns)
            if key not in _highlight_cache:
                if len(_highlight_cache) > 200:
                    _highlight_cache.clear()
                _highlight_cache[key] = highlight_mod.highlight(path, file["content"])
            tokens = _highlight_cache[key]
            file["tokens"] = tokens["lines"] if tokens else None
            file["language"] = tokens["language"] if tokens else None
        return file
    except repo_mod.RepoError as exc:
        raise HTTPException(400, str(exc)) from exc


# ------------------------------------------------------------------ the claude terminal (proxied to its own container)

def fetch_claude_result(session_id: str) -> dict:
    """Ask the terminal service what claude saved in its live working copy: {"found", "text", "name", "new_files"}."""
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        return {"found": False, "text": "", "name": "", "new_files": []}
    import httpx

    with httpx.Client(trust_env=False, timeout=5) as client:
        response = client.get(f"{TERMINAL_URL}/result", params={"sid": session_id}, headers={"x-terminal-token": TERMINAL_TOKEN})
    response.raise_for_status()
    return response.json()


def fetch_claude_review(session_id: str) -> str | None:
    data = fetch_claude_result(session_id)
    return data["text"] if data.get("found") and data["text"].strip() else None


def apply_claude_review(session: Session) -> None:
    """Turn the structured block at the end of claude's report into assessments, corrections, improvements and a verdict."""
    root = repo_dir(session)
    files = line_index(root) if root is not None else {}
    report, reviews = parse_report(session.claude_review, session.review_items, files)
    with store.lock:
        kept = {k: v for k, v in session.ai.reviews.items() if v.by != "Claude"}
        session.ai.reviews = {**kept, **reviews}
        session.claude = report


def ensure_review_files(session: Session) -> bool:
    """Make sure verdict.md and claude-review.md exist in the clone whenever there is a review to show.
    (A review stored before the file existed, or a file deleted by hand, is healed here.)"""
    root = repo_dir(session)
    if root is None or not session.claude_review.strip():
        return False
    if session.claude_review_file and (root / session.claude_review_file).is_file():
        return False
    write_verdict(session)
    store.save(session)
    return True


def collect_claude_review(session: Session) -> bool:
    """Store claude's saved report in the session and write it into the clone. False when there was nothing new."""
    try:
        text = fetch_claude_review(session.id)
    except Exception:
        return False
    if text and text != session.claude_review:
        with store.lock:
            session.claude_review, session.claude_review_at = text, _now()
        apply_claude_review(session)
        write_verdict(session)
        store.save(session)
        return True
    return ensure_review_files(session)


@app.post("/api/sessions/{session_id}/claude-review/save")
def save_claude_review(session_id: str) -> dict:
    """Write what claude saved in the open terminal into the clone: claude-review.md, and the end of verdict.md."""
    session = session_or_404(session_id)
    if not session.results:
        raise HTTPException(400, "run the checks first")
    try:
        data = fetch_claude_result(session_id)
    except Exception as exc:
        raise HTTPException(503, "could not reach the terminal service") from exc
    text = fetch_claude_review(session_id) if not data.get("found") else data["text"]      # (tests replace fetch_claude_review)
    if not text or not text.strip():
        made = data.get("new_files") or []
        raise HTTPException(404, "claude has not saved its report yet. Ask it to save it as claude-review.md and approve the write, then try again."
                            + (f" Files it created so far: {', '.join(made)}." if made else " It has not created any file yet."))
    changed = text != session.claude_review
    with store.lock:
        if changed:
            session.claude_review, session.claude_review_at = text, _now()
    if changed or not session.claude.structured:
        apply_claude_review(session)   # (also re-reads a report stored before the numbering existed)
    write_verdict(session)             # always: an unchanged report must still be written if the file is missing
    store.save(session)
    return {"saved": bool(session.claude_review_file), "changed": changed, "chars": len(text), "verdict_file": session.verdict_file,
            "review_file": session.claude_review_file, "source_name": data.get("name") or "claude-review.md",
            "structured": session.claude.structured, "assessed": session.claude.assessed, "total": session.claude.total,
            "problems": session.claude.problems,
            "warning": "" if session.claude_review_file else
            "The review was stored, but it could not be written into the repository (a file named claude-review.md already exists there and is not ours, or it is a link)."}




REPORT_POLL_SECONDS = 4
TERMINAL_URL = os.environ.get("TERMINAL_URL", "").rstrip("/")
TERMINAL_TOKEN = os.environ.get("TERMINAL_TOKEN", "")


async def open_upstream(url: str, token: str):
    """Connect to the terminal service (replaced in tests)."""
    import websockets

    return await websockets.connect(url, additional_headers={"x-terminal-token": token}, max_size=2**20, open_timeout=10,
                                    proxy=None)  # an internal service: never through an HTTP proxy from the environment


@app.get("/api/terminal")
def terminal_status() -> dict:
    """Is the terminal container configured and reachable, and is `claude` installed in it?"""
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        return {"configured": False, "reachable": False, "claude": False}
    try:
        import httpx

        with httpx.Client(trust_env=False, timeout=3) as client:      # internal service: ignore proxy variables
            response = client.get(f"{TERMINAL_URL}/health")
        data = response.json()
        if response.status_code != 200 or data.get("status") != "ok":
            raise ValueError("unexpected answer")
        return {"configured": True, "reachable": True, "claude": bool(data.get("claude"))}
    except Exception:
        return {"configured": True, "reachable": False, "claude": False}


def same_origin(ws: WebSocket) -> bool:
    """Browsers always send Origin on a WebSocket; refuse any page that is not served by this app (cross-site hijacking)."""
    origin = ws.headers.get("origin")
    return bool(origin) and urlparse(origin).netloc == ws.headers.get("host")


@app.websocket("/api/sessions/{session_id}/terminal")
async def terminal_proxy(ws: WebSocket, session_id: str) -> None:
    if not same_origin(ws):
        await ws.close(code=4403)
        return
    try:
        session = store.get(session_id)
    except KeyError:
        await ws.close(code=4404)
        return
    if not session.repo or not session.repo.path:
        await ws.close(code=4404)
        return
    await ws.accept()
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        await ws.send_bytes(b"\r\n[terminal] not configured. Start the app with `make run`.\r\n")
        await ws.close()
        return
    url = (TERMINAL_URL.replace("http", "ws", 1) + f"/pty?repo={quote(session.repo.path)}"
           f"&cols={int(ws.query_params.get('cols', 80))}&rows={int(ws.query_params.get('rows', 24))}")
    url += f"&sid={session_id}"
    prompt_id = ws.query_params.get("prompt", "")
    if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", prompt_id):
        url += f"&prompt={prompt_id}"
    try:
        upstream = await open_upstream(url, TERMINAL_TOKEN)
    except Exception:
        await ws.send_bytes(b"\r\n[terminal] cannot reach the terminal service. Is it running? Start everything with `make run`.\r\n")
        await ws.close()
        return

    async def to_browser() -> None:
        async for message in upstream:
            await ws.send_bytes(message if isinstance(message, bytes) else message.encode())

    async def to_terminal() -> None:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes") if message.get("bytes") is not None else message.get("text")
            if data is not None and len(data) <= 65536:
                await upstream.send(data)

    async def watch_for_report() -> None:
        """Every few seconds: has claude saved its report? Then it goes into the clone straight away."""
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(REPORT_POLL_SECONDS)
            try:
                await loop.run_in_executor(None, collect_claude_review, session)
            except Exception:
                pass

    tasks = [asyncio.create_task(to_browser()), asyncio.create_task(to_terminal()), asyncio.create_task(watch_for_report())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        try:
            # Collect claude's saved report before the working copy is deleted. The thread starts at once; shield and
            # catch cancellation, because this block also runs while the connection's task is being cancelled.
            await asyncio.shield(asyncio.get_running_loop().run_in_executor(None, collect_claude_review, session))
        except (Exception, asyncio.CancelledError):
            pass
        try:
            await upstream.close()
        except Exception:
            pass
        try:
            await ws.close()
        except RuntimeError:
            pass


def review_prompt_for(session: Session) -> tuple[str, dict]:
    if not session.results or session.repo is None:
        raise HTTPException(400, "run the checks first")
    session.review_items = manual_items(session.results)        # claude answers by these numbers
    store.save(session)
    return build_review_prompt(project=session.repo.name or session.repo.path, subjects=list(session.subjects),
                               lang=session.lang(), results=session.results)


@app.get("/api/sessions/{session_id}/review-prompt")
def review_prompt(session_id: str) -> dict:
    """The review request for claude, built from what the checks did and did not cover."""
    text, stats = review_prompt_for(session_or_404(session_id))
    return {"text": text, **stats}


@app.post("/api/sessions/{session_id}/terminal-prompt")
def terminal_prompt(session_id: str) -> dict:
    """Hand the review request to the terminal service so that a NEW claude session starts with it."""
    session = session_or_404(session_id)
    text, stats = review_prompt_for(session)
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        raise HTTPException(503, "the terminal is not configured; start the app with `make run`")
    try:
        import httpx

        with httpx.Client(trust_env=False, timeout=5) as client:
            response = client.post(f"{TERMINAL_URL}/prompts", json={"text": text}, headers={"x-terminal-token": TERMINAL_TOKEN})
        response.raise_for_status()
        return {"id": response.json()["id"], **stats}
    except Exception as exc:
        raise HTTPException(503, "could not reach the terminal service") from exc


# ------------------------------------------------------------------ the verdict document


def verdict_text(session: Session) -> str:
    return render_markdown(
        repo=session.repo.model_dump() if session.repo else None,
        subjects=list(session.subjects),
        results=session.results,
        improvements=chosen_improvements(session),
        readme=session.readme or None,
        ai=session.ai,
        claude_review=session.claude_review,
        claude=session.claude,
        claude_file=session.claude_review_file,
        project=(session.repo.name or session.repo.path) if session.repo else "",
    )


def write_generated(session: Session, names: tuple[str, str], text: str) -> str:
    """Save `text` into the reviewed repository as names[0] (or names[1] when the project already has its own file of that
    name). Never overwrites a file that is not ours and never writes through a symlink. Returns the name used, or ""."""
    root = repo_dir(session)
    if root is None or not root.is_dir():
        return ""
    for name in names:
        target = root / name
        if target.is_symlink():
            continue  # a link could point outside the repository
        if target.exists():
            try:
                if not target.read_bytes()[:200].startswith(VERDICT_MARKER.encode()):
                    continue  # the project's own file
            except OSError:
                continue
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o644)
        except OSError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        return name
    return ""


def write_verdict(session: Session) -> None:
    """Save claude's review (when there is one) and the verdict inside the reviewed repository.
    claude-review.md goes first so that verdict.md can point to it by its real name."""
    if session.claude_review.strip():
        session.claude_review_file = write_generated(
            session, ("claude-review.md", "claude-review-report.md"),
            f"{VERDICT_MARKER}\n\n{session.claude_review.strip()}\n")
    else:
        session.claude_review_file = ""
    session.verdict_file = write_generated(session, ("verdict.md", "verdict-report.md"), verdict_text(session))
    if not session.verdict_file and repo_dir(session) is not None:
        session.message = "Could not save the verdict into the repository (no writable file name)."


# ------------------------------------------------------------------ running checks


def make_work_copy(session: Session, clone: Path) -> Path:
    """A disposable copy of the clone, where the checks build and run things. The clone itself is never built in,
    so it always shows exactly what was committed (no .o files or binaries left over from a previous run)."""
    work = WORKSPACE / session.id / "work"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(clone, work, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    return work


def _run(session: Session) -> None:
    clone = repo_dir(session).resolve()
    work: Path | None = None

    def emit(result: CheckResult) -> None:
        with store.lock:
            session.results.append(result)

    try:
        work = make_work_copy(session, clone)
        run_checks(Ctx(repo=work.resolve(), rules=session.rules(), sandbox=sandbox, lang=session.lang()), emit)
        # Suggestions and the README look at what was committed, not at what building left behind.
        pristine = Ctx(repo=clone, rules=session.rules(), sandbox=None, lang=session.lang())
        session.improvements = improve_mod.suggest(pristine)
        session.readme = improve_mod.readme_status(pristine)
        write_verdict(session)
        session.state, session.message = "done", session.message
    except Exception as exc:
        session.state, session.message = "error", f"{type(exc).__name__}: {exc}"
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
    store.save(session)


@app.post("/api/sessions/{session_id}/run")
def run(session_id: str) -> dict:
    session = session_or_404(session_id)
    if session.state in ("cloning", "running"):
        raise HTTPException(409, f"session is busy ({session.state})")
    if not session.repo:
        raise HTTPException(400, "clone a repository first")
    if not session.subjects:
        raise HTTPException(400, "add at least one subject PDF first")
    session.results, session.improvements, session.state, session.message = [], [], "running", ""
    session.ai = AIState(reviews={k: v for k, v in session.ai.reviews.items() if v.by == "Claude"})
    threading.Thread(target=_run, args=(session,), daemon=True).start()
    return view(session)


# ------------------------------------------------------------------ AI review


def _check_summary(session: Session) -> str:
    counts = summarize(session.results)
    lines = [f"Result: {counts['overall']}",
             "mandatory: " + ", ".join(f"{k} {v}" for k, v in counts["mandatory"].items()),
             "bonus: " + ", ".join(f"{k} {v}" for k, v in counts["bonus"].items())]
    failed = [r.title + (f" ({r.detail[:100]})" if r.detail else "") for r in session.results if r.status == "fail"][:15]
    if failed:
        lines.append("Failed checks:\n" + "\n".join(f"- {t}" for t in failed))
    return "\n".join(lines)


_ai_jobs: dict[str, ai_mod.Job] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _note(session: Session, state: AIState, text: str) -> None:
    """Record what the review is doing (ignored once it was cancelled or replaced)."""
    with store.lock:
        if session.ai is state and state.state == "running":
            state.step = text
            state.progress.append(AIEvent(at=_now(), text=text))
            del state.progress[:-120]


def _run_ai(session: Session, state: AIState, job: ai_mod.Job) -> None:
    def current() -> bool:
        return session.ai is state and state.state == "running"

    try:
        root = repo_dir(session)
        limit = int(os.environ.get("LLM_MAX_CHARS") or (100_000 if ai_mod.provider() == "openai" else 150_000))
        if ai_mod.provider() == "claude-cli":
            digest = Digest(text="", lines=line_index(root))           # claude reads the files itself; this only validates citations
            job.notify(f"claude will explore {len(digest.lines)} files itself with read-only tools")
        else:
            job.notify(f"Reading the repository (sending at most {limit:,} characters)")
            digest = build_digest(root, limit)
            job.notify(f"Prepared {len(digest.included)} files, {len(digest.text):,} characters"
                       + (f"; {len(digest.truncated)} cut, {len(digest.omitted)} left out" if digest.truncated or digest.omitted else ""))
        backend, usage = ai_mod.make_client(repo=session.repo.path), ai_mod.Usage()
        backend.job = job
        known = [i.title for i in session.improvements if i.source == "static"]
        overview, improvements = ai_mod.analyze(backend, digest, subjects=list(session.subjects),
                                                summary=_check_summary(session), known_titles=known, usage=usage)
        job.notify(f"Overview ready; kept {len(improvements)} improvement idea(s) whose citations check out")
        manual: dict[str, str] = {}
        for r in session.results:
            if r.status == "manual" and r.rule_id and r.rule_id not in manual:
                manual[r.rule_id] = r.detail or r.title
        reviews = ai_mod.review(backend, digest, list(manual.items())[:60], usage) if manual else {}
        with store.lock:
            if not current():
                return  # cancelled or replaced while the last request was in flight: drop the result
            state.model = backend.model                   # may differ from the configured one after a fallback
            state.overview, state.reviews = overview, reviews
            state.input_tokens, state.output_tokens = usage.input_tokens, usage.output_tokens
            state.not_fully_sent = digest.truncated + digest.omitted
            state.generated_at = _now()
            session.improvements = sorted(
                [i for i in session.improvements if i.source != "ai"] + improvements,
                key=lambda i: improve_mod.PRIORITY_ORDER[i.priority])
            state.progress.append(AIEvent(at=_now(), text=f"Done: {len(reviews)} item(s) assessed with {backend.model}"))
            state.step, state.state, state.message = "", "done", ""
        write_verdict(session)
    except ai_mod.Cancelled:
        pass  # the cancel endpoint already recorded it
    except ai_mod.AIError as exc:
        with store.lock:
            if current():
                state.state, state.message, state.step = "error", str(exc), ""
                state.progress.append(AIEvent(at=_now(), text=f"Failed: {exc}"))
    except Exception:
        logging.getLogger("verdict").exception("AI review failed")
        with store.lock:
            if current():
                state.state, state.message, state.step = "error", "Unexpected error during the AI review (see the server log).", ""
    finally:
        if _ai_jobs.get(session.id) is job:
            del _ai_jobs[session.id]
    store.save(session)


@app.post("/api/sessions/{session_id}/ai")
def start_ai(session_id: str) -> dict:
    session = session_or_404(session_id)
    if not ai_mod.configured():
        raise HTTPException(400, "The AI review is not configured. Set ANTHROPIC_API_KEY, or LLM_BASE_URL + LLM_API_KEY + LLM_MODEL, in .env (see the README).")
    if session.state in ("cloning", "running") or session.ai.state == "running":
        raise HTTPException(409, "something is already running")
    if not session.results or repo_dir(session) is None:
        raise HTTPException(400, "run the checks first")
    state = AIState(state="running", model=ai_mod.model_name(), started_at=_now(), job=session.ai.job + 1)
    session.ai = state
    job = ai_mod.Job(notify=lambda text: _note(session, state, text))
    _ai_jobs[session.id] = job
    _note(session, state, f"Starting the AI review with {state.model} via {ai_mod.endpoint_host()}")
    threading.Thread(target=_run_ai, args=(session, state, job), daemon=True).start()
    return view(session)


@app.post("/api/sessions/{session_id}/ai/cancel")
def cancel_ai(session_id: str) -> dict:
    session = session_or_404(session_id)
    state = session.ai
    with store.lock:
        if state.state == "running":
            state.progress.append(AIEvent(at=_now(), text="Stopped by you"))
            state.state, state.message, state.step = "cancelled", "Stopped by you.", ""
            job = _ai_jobs.get(session_id)
            if job:
                job.cancel.set()
    store.save(session)
    return view(session)


@app.get("/api/sessions/{session_id}/verdict.md", response_class=PlainTextResponse)
def verdict_md(session_id: str, download: bool = False) -> PlainTextResponse:
    session = session_or_404(session_id)
    headers = {"Content-Disposition": 'attachment; filename="verdict.md"'} if download else {}
    return PlainTextResponse(verdict_text(session), media_type="text/markdown; charset=utf-8", headers=headers)


static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
