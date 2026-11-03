from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai as ai_mod
from . import highlight as highlight_mod
from . import improve as improve_mod
from . import repo as repo_mod
from .digest import Digest, build_digest, line_index
from .claude_report import parse_report
from .prompts import build_fix_prompt, build_review_prompt, find_docker_files, manual_items
from .shared import TERMINAL_REPORTS_ROOT, TERMINAL_SUBJECTS_ROOT
from .checks import EXCLUDED_DIRS, VERDICT_MARKER, Ctx, run_checks
from .models import CheckResult
from .pdfread import read_pages, render_page
from .report import render_markdown, summarize
from .sandbox import Sandbox, SandboxError, sandbox_selftest
from .selftest import summarize as selftest_summary
from .spec import parse_norm, parse_subject
from .models import AIEvent, AIState, ClaudeReport
from .store import RepoMeta, Session, Store, Subject, safe_filename

WORKSPACE = Path(os.environ.get("WORKSPACE", "workspace")).resolve()
PROJECTS = Path(os.environ.get("PROJECTS_DIR", WORKSPACE / "projects")).resolve()
PROJECTS.mkdir(parents=True, exist_ok=True)
SAMPLES = Path(os.environ.get("SAMPLES_DIR", "/samples" if Path("/samples").is_dir() else "samples")).resolve()
# The library: one folder per curriculum track, and the Norm at the root (applied to every C project).
TRACKS = {"common-core": "Common Core", "post-common-core": "Post Common Core", "rncp": "RNCP"}
NORM_PDF = "en.norm.pdf"
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
            {"name": s.name, "kind": s.kind, "track": s.track, "lang": s.lang, "pages": s.pages, "rules": [r.model_dump() for r in s.rules]}
            for s in session.subjects.values()
        ],
        "results": [r.model_dump() for r in session.results],
        "improvements": [i.model_dump() for i in chosen_improvements(session)],
        "claude": session.claude.model_dump(),
        "readme": session.readme,
        "verdict_file": session.verdict_file,
        "claude_review_at": session.claude_review_at,
        "ai": session.ai.model_dump(),
        "summary": summarize(session.results, session.ai, session.claude),
    }


# ------------------------------------------------------------------ environment


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "sandbox": bool(sandbox and sandbox.healthy()),
            "llm": {"configured": ai_mod.configured(), "model": ai_mod.model_name(), "provider": ai_mod.provider(), "host": ai_mod.endpoint_host()}}


@app.get("/api/environment")
def environment(deep: bool = False) -> dict:
    """Can the sandbox AND claude's terminal really build and run things? C, C++, make, docker (client and daemon).
    `deep` also builds and runs a tiny Dockerfile on the separate daemon (needs internet, so only on request)."""
    now = time.monotonic()
    cached = _environment_cache.get(deep)
    if cached and now - cached[0] < 20:
        return cached[1]
    answer: dict = {}
    if sandbox is None:
        answer["sandbox"] = {"available": False, "tools": [], "summary": selftest_summary([]), "error": "the sandbox is not configured"}
    else:
        try:
            tools = sandbox_selftest(sandbox, WORKSPACE, deep=deep)
            answer["sandbox"] = {"available": True, "tools": tools, "summary": selftest_summary(tools)}
        except (SandboxError, OSError) as exc:
            answer["sandbox"] = {"available": False, "tools": [], "summary": selftest_summary([]), "error": str(exc)}
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        answer["terminal"] = {"available": False, "tools": [], "summary": selftest_summary([]), "error": "the terminal is not configured"}
    else:
        try:
            import httpx

            with httpx.Client(trust_env=False, timeout=360 if deep else 90) as client:
                response = client.get(f"{TERMINAL_URL}/selftest", params={"deep": deep}, headers={"x-terminal-token": TERMINAL_TOKEN})
            response.raise_for_status()
            tools = response.json()["tools"]
            answer["terminal"] = {"available": True, "tools": tools, "summary": selftest_summary(tools)}
        except Exception as exc:
            answer["terminal"] = {"available": False, "tools": [], "summary": selftest_summary([]), "error": f"could not reach the terminal service ({type(exc).__name__})"}
    parts = [answer["sandbox"], answer["terminal"]]
    answer["ready"] = all(p["available"] and p["summary"]["ready"] for p in parts)
    answer["deep"] = deep
    _environment_cache[deep] = (now, answer)
    return answer


_environment_cache: dict = {}


def library_files() -> dict[str, Path]:
    """Subject PDFs in the library, by their path inside it (`common-core/libft.pdf`)."""
    found: dict[str, Path] = {}
    for track in TRACKS:
        folder = SAMPLES / track
        if folder.is_dir():
            for p in sorted(folder.glob("*.pdf")):
                if p.is_file() and not p.is_symlink():
                    found[f"{track}/{p.name}"] = p
    return found


@app.get("/api/library")
def library() -> dict:
    """Subject PDFs bundled with the deployment (./samples/<track>/), and whether the Norm (./samples/en.norm.pdf) is there."""
    return {
        "tracks": [{"id": track, "label": label} for track, label in TRACKS.items()],
        "items": [{"path": rel, "name": p.name, "track": rel.split("/", 1)[0], "size": p.stat().st_size}
                  for rel, p in library_files().items()],
        "norm": (SAMPLES / NORM_PDF).is_file(),
    }


# ------------------------------------------------------------------ sessions


@app.post("/api/sessions")
def create_session() -> dict:
    return view(store.create())


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = session_or_404(session_id)
    if drop_stale_reviews(session):   # a review of another repository or subject set never reaches this verdict
        if session.results:
            write_verdict(session)
        store.save(session)
    ensure_review_files(session)      # a stored review whose file is missing from the clone is written out
    return view(session)


def _add_subject(session: Session, name: str, data: bytes, track: str = "") -> None:
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, f"{name} is not a PDF")
    if name == NORM_PDF:
        raise HTTPException(400, f"{NORM_PDF} is the Norm: it is added automatically whenever C code is detected")
    if len(session.subjects) >= MAX_SUBJECTS and name not in session.subjects:
        raise HTTPException(400, f"at most {MAX_SUBJECTS} subjects per session")
    try:
        pages = read_pages(data)
    except Exception as exc:
        raise HTTPException(400, f"could not read {name}: {exc}") from exc
    spec = parse_subject(name, pages)
    session.subjects[name] = Subject(name=name, track=track, lang=spec.lang, pages=len(pages), rules=spec.rules)
    session.results = []
    session.state = "idle"
    kept = subjects_dir(session) / name           # a copy of its own, so the PDF can be shown in the app
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_bytes(data)


def subjects_dir(session: Session) -> Path:
    return store.path(session.id) / "subjects"


def refresh_subject_files(session: Session) -> Path:
    """The folder with the PDFs of this review: the subjects you chose or uploaded, and the Norm while it applies, and nothing else.
    The sandbox reads it as $SUBJECTS_DIR for the checks and the terminal container gets a copy of it (push_subjects)."""
    folder = subjects_dir(session)
    folder.mkdir(parents=True, exist_ok=True)
    for name in session.subjects:
        target = folder / name
        try:
            source = subject_pdf(session, name)
        except HTTPException:
            continue                                       # the file is gone (an old session): nothing to hand over
        if source.resolve() != target.resolve() and (not target.exists() or target.stat().st_size != source.stat().st_size):
            data = source.read_bytes()
            fd, temporary = tempfile.mkstemp(dir=folder, prefix=".copy-")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.chmod(temporary, 0o444)                     # read-only for anything that runs in the sandbox by accident
            os.replace(temporary, target)
    for stale in folder.iterdir():
        if stale.is_file() and not stale.is_symlink() and stale.suffix.lower() == ".pdf" and stale.name not in session.subjects:
            stale.unlink(missing_ok=True)                  # a subject that was removed, or the Norm when C is no longer detected
    return folder


def subject_pdf(session: Session, name: str) -> Path:
    """The PDF of a subject of this session: its own copy, or the library file (sessions made before copies were kept)."""
    subject = session.subjects.get(name)
    if subject is None:
        raise HTTPException(404, f"{name} is not a subject of this session")
    candidates = [subjects_dir(session) / name]
    if subject.kind == "norm":
        candidates.append(SAMPLES / NORM_PDF)
    elif subject.track in TRACKS:
        candidates.append(SAMPLES / subject.track / name)
    for path in candidates:
        if path.is_file() and not path.is_symlink():
            return path
    raise HTTPException(404, f"the PDF of {name} is no longer available; add it again")


def library_slot(track: str, name: str, data: bytes) -> Path | None:
    """Where an upload goes in samples/<track>/, or None when that exact file is already there.
    An existing file with other content (or a link) is never replaced."""
    target = SAMPLES / track / name
    if target.is_symlink():
        raise HTTPException(409, f"samples/{track}/{name} is a link; it was not replaced")
    if target.exists():
        if target.read_bytes() == data:
            return None
        raise HTTPException(409, f"samples/{track}/{name} already exists with different content. "
                                 "Rename the file, or remove the old one from the folder first.")
    return target


def save_to_library(target: Path, data: bytes) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.upload")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    except OSError as exc:
        raise HTTPException(500, f"could not save {target.name} into samples/{target.parent.name}/: {exc.strerror}") from exc


_norm_cache: dict = {}


def norm_subject() -> Subject | None:
    """The Norm from samples/en.norm.pdf (parsed once per version of the file), or None when it is missing."""
    path = SAMPLES / NORM_PDF
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (stat.st_mtime_ns, stat.st_size)
    if _norm_cache.get("key") != key:
        pages = read_pages(path.read_bytes())
        spec = parse_norm(NORM_PDF, pages)
        _norm_cache.update(key=key, subject=Subject(name=NORM_PDF, kind="norm", lang=spec.lang, pages=len(pages), rules=spec.rules))
    return _norm_cache["subject"].model_copy(deep=True)


def refresh_subject_rules(session: Session) -> bool:
    """Read every subject's PDF again with the parser as it is now. The rules are stored in the session when a subject is added, so
    without this an improvement of the parser would never reach a review that already had the subject (it would keep showing the old
    findings until the subject was removed and added again). A subject whose PDF is gone keeps the rules it has. True when something changed."""
    changed = False
    for name, subject in list(session.subjects.items()):
        try:
            if subject.kind == "norm":
                fresh = norm_subject()
                if fresh is None:
                    continue
            else:
                pages = read_pages(subject_pdf(session, name))
                spec = parse_subject(name, pages)
                fresh = Subject(name=name, track=subject.track, lang=spec.lang, pages=len(pages), rules=spec.rules)
        except Exception:                                  # (an unreadable or missing PDF: keep what the session has)
            continue
        if (fresh.rules, fresh.lang, fresh.pages) != (subject.rules, subject.lang, subject.pages):
            session.subjects[name] = fresh
            changed = True
    return changed


def has_c_code(session: Session) -> bool:
    """C is detected when a subject requires it or, with no language in the subjects, when the repo has C and no C++."""
    lang = session.lang()
    if lang:
        return lang == "c"
    root = repo_dir(session)
    if root is None or not root.is_dir():
        return False
    exts = {p.suffix.lower() for p in repo_mod.tracked_files(root) if not EXCLUDED_DIRS.search("/" + p.as_posix())}
    return ".c" in exts and not exts & {".cpp", ".cc", ".hpp", ".tpp", ".ipp"}


def sync_norm(session: Session) -> None:
    """Attach the Norm whenever C code is detected, and take it away when it is not."""
    attached = session.subjects.get(NORM_PDF)
    if has_c_code(session):
        if attached is None or attached.kind != "norm":
            norm = norm_subject()
            if norm is not None:
                session.subjects[NORM_PDF] = norm
                session.results = []
    elif attached is not None and attached.kind == "norm":
        del session.subjects[NORM_PDF]
        session.results = []


def review_context(session: Session) -> str:
    """What a review is about: the cloned commit and the subjects. A review made for another context is stale."""
    repo = session.repo
    subjects = sorted(name for name, s in session.subjects.items() if s.kind == "subject")
    return json.dumps([[repo.url, repo.path, repo.commit] if repo else None, subjects])


def drop_stale_reviews(session: Session) -> bool:
    """Forget claude's review and the AI review when they were made for another repository, commit or set of subjects
    (e.g. libft's review must never show up in the verdict of the next project). True when something was dropped."""
    has_reviews = session.claude_review or session.review_items or session.ai.state != "idle" or session.ai.reviews
    if not has_reviews or session.review_context == review_context(session):
        return False
    job = _ai_jobs.pop(session.id, None)
    if job:
        job.cancel.set()
    with store.lock:
        session.ai = AIState(job=session.ai.job + 1)
        session.claude_review = session.claude_review_at = ""
        session.claude = ClaudeReport()
        session.review_items = []
        session.review_context = ""
    return True


def refresh_context(session: Session) -> None:
    """After the repository or the subjects changed: attach or remove the Norm, and drop reviews of the old context."""
    sync_norm(session)
    drop_stale_reviews(session)


@app.post("/api/sessions/{session_id}/subjects")
async def upload_subjects(session_id: str, files: list[UploadFile] = File(...), track: str = Form(...)) -> dict:
    """Add uploaded subjects to the session and keep them in the library folder of the chosen track."""
    session = session_or_404(session_id)
    if track not in TRACKS:
        raise HTTPException(400, f"choose where the subject belongs: {', '.join(TRACKS.values())}")
    for upload in files:
        data = await upload.read(MAX_PDF_BYTES + 1)
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(413, f"{upload.filename} is larger than {MAX_PDF_BYTES // 2**20} MB")
        name = safe_filename(upload.filename or "subject.pdf")
        target = library_slot(track, name, data)
        _add_subject(session, name, data, track)
        if target is not None:
            save_to_library(target, data)
    refresh_context(session)
    store.save(session)
    return view(session)


class LibraryPick(BaseModel):
    paths: list[str]


@app.post("/api/sessions/{session_id}/subjects/library")
def add_from_library(session_id: str, pick: LibraryPick) -> dict:
    session = session_or_404(session_id)
    available = library_files()
    for rel in pick.paths:
        if rel not in available:
            raise HTTPException(404, f"{rel} is not in the library")
        _add_subject(session, available[rel].name, available[rel].read_bytes(), rel.split("/", 1)[0])
    refresh_context(session)
    store.save(session)
    return view(session)


@app.delete("/api/sessions/{session_id}/subjects/{name}")
def remove_subject(session_id: str, name: str) -> dict:
    session = session_or_404(session_id)
    subject = session.subjects.get(name)
    if subject is not None and subject.kind == "norm":
        raise HTTPException(400, "The Norm applies to every C project; it goes away by itself when no C is detected.")
    session.subjects.pop(name, None)
    (subjects_dir(session) / safe_filename(name)).unlink(missing_ok=True)
    session.results = []
    refresh_context(session)
    store.save(session)
    return view(session)


_page_cache: dict = {}


@app.get("/api/sessions/{session_id}/subjects/{name}/pages/{page}.png")
def subject_page(session_id: str, name: str, page: int) -> Response:
    """One page of a subject PDF as an image, for the PDF tab (the CSP allows images, not embedded PDF viewers)."""
    path = subject_pdf(session_or_404(session_id), name)
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size, page)
    if key not in _page_cache:
        try:
            png = render_page(path, page)
        except IndexError:
            raise HTTPException(404, f"{name} has no page {page}") from None
        if len(_page_cache) > 120:
            _page_cache.clear()
        _page_cache[key] = png
    return Response(_page_cache[key], media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


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


class ExistingRequest(BaseModel):
    path: str


@app.get("/api/projects/existing")
def existing_projects() -> dict:
    """Folders already in the projects folder that can be reviewed without cloning."""
    return {"root": PROJECTS.name, "folders": repo_mod.list_existing(PROJECTS)}


@app.post("/api/sessions/{session_id}/repo/existing")
def use_existing_repo(session_id: str, req: ExistingRequest) -> dict:
    """Review a folder that is already in the projects folder instead of cloning one."""
    session = session_or_404(session_id)
    if session.state in ("cloning", "running"):
        raise HTTPException(409, f"session is busy ({session.state})")
    try:
        path, info = repo_mod.use_existing(PROJECTS, req.path)
    except repo_mod.RepoError as exc:
        raise HTTPException(400, str(exc)) from exc
    session.repo = RepoMeta(**info.__dict__, name=path.name, path=path.relative_to(PROJECTS.resolve()).as_posix())
    session.results, session.state, session.message = [], "idle", ""
    refresh_context(session)
    store.save(session)
    return view(session)


@app.post("/api/sessions/{session_id}/repo/pull")
def pull_repo(session_id: str) -> dict:
    """git pull (fast-forward only) in the project being reviewed, through the ssh-agent, then show the new commit."""
    session = session_or_404(session_id)
    if session.state in ("cloning", "running"):
        raise HTTPException(409, f"session is busy ({session.state})")
    root = repo_dir(session)
    if root is None or not root.is_dir():
        raise HTTPException(404, "no repository to pull")
    try:
        info, summary = repo_mod.pull(root, WORKSPACE / "known_hosts")
    except repo_mod.RepoError as exc:
        raise HTTPException(400, str(exc)) from exc
    changed = info.commit != session.repo.commit
    session.repo = RepoMeta(**info.__dict__, name=session.repo.name, path=session.repo.path)
    if changed:
        session.state, session.message = "idle", ""
    refresh_context(session)
    store.save(session)
    return {**view(session), "pull": {"changed": changed, "summary": summary}}

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
    refresh_context(session)
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
        session.review_context = review_context(session)


_GENERATED_LINE = re.compile(r"^- Generated: .*$", re.M)


def verdict_file_is_current(path: Path, text: str) -> bool:
    """Does the verdict.md on disk say what the app says now? (Only the 'Generated' time may differ.) A file that is not
    ours, or that cannot be read, is left alone and counts as current."""
    try:
        if path.is_symlink() or not path.is_file():
            return False
        disk = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    if not disk.startswith(VERDICT_MARKER):
        return True
    return _GENERATED_LINE.sub("", disk).strip() == _GENERATED_LINE.sub("", text).strip()


def ensure_review_files(session: Session) -> bool:
    """Keep verdict.md in the clone the same as the verdict shown in the app: it is written again when it is missing or no
    longer says what the app says (the verdict can change after it was written), and a claude-review.md left by an earlier
    version is removed. Never while a run is in progress."""
    root = repo_dir(session)
    if root is None or not session.results or session.state == "running" or session.ai.state == "running":
        return False
    if (session.verdict_file and not any(is_generated(root / name) for name in OLD_REVIEW_FILES)
            and verdict_file_is_current(root / session.verdict_file, verdict_text(session))):
        return False
    write_verdict(session)
    store.save(session)
    return True


def collect_claude_review(session: Session, context: str | None = None) -> bool:
    """Store claude's saved report in the session and merge it into verdict.md. False when there was nothing new.
    `context` is what the terminal was opened for: a report from a terminal of another repository or subject set is ignored."""
    if context is not None and context != review_context(session):
        return False
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
    """Merge what claude saved in the open terminal into verdict.md in the clone (no separate file is written)."""
    return merge_claude_review(session_or_404(session_id))


def merge_claude_review(session: Session) -> dict:
    """Force claude's saved report into the session and into verdict.md in the project, whatever happened before: a report the
    automatic pickup missed, or one made for another commit (it is adopted for the project as it is now). Raises an HTTPException
    that says why when there is nothing to merge."""
    session_id = session.id
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
    return {"saved": bool(session.verdict_file), "changed": changed, "chars": len(text), "verdict_file": session.verdict_file,
            "source_name": data.get("name") or "claude-review.md",
            "structured": session.claude.structured, "assessed": session.claude.assessed, "total": session.claude.total,
            "problems": session.claude.problems,
            "warning": "" if session.verdict_file else
            "The review was stored, but verdict.md could not be written into the repository (files of that name exist there and are not ours, or they are links)."}




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
    """Is the terminal container configured and reachable, is `claude` installed in it, and does it work in your project folder
    ("live") or in a throw-away copy ("copy")?"""
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        return {"configured": False, "reachable": False, "claude": False, "workdir": "copy"}
    try:
        import httpx

        with httpx.Client(trust_env=False, timeout=3) as client:      # internal service: ignore proxy variables
            response = client.get(f"{TERMINAL_URL}/health")
        data = response.json()
        if response.status_code != 200 or data.get("status") != "ok":
            raise ValueError("unexpected answer")
        return {"configured": True, "reachable": True, "claude": bool(data.get("claude")),
                "workdir": "live" if data.get("workdir") == "live" else "copy"}
    except Exception:
        return {"configured": True, "reachable": False, "claude": False, "workdir": "copy"}


def same_origin(ws: WebSocket) -> bool:
    """Browsers always send Origin on a WebSocket; refuse any page that is not served by this app (cross-site hijacking)."""
    origin = ws.headers.get("origin")
    return bool(origin) and urlparse(origin).netloc == ws.headers.get("host")


def push_subjects(session: Session) -> None:
    """Hand this review's PDFs to the terminal container, which cannot see the workspace. Only when it does not already have exactly
    these files. Best effort: a terminal without the PDFs is still a working terminal."""
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        return
    try:
        import httpx

        folder = refresh_subject_files(session)
        files = {p.name: p for p in sorted(folder.glob("*.pdf")) if p.is_file() and not p.is_symlink() and p.name in session.subjects}
        digests = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
        headers = {"x-terminal-token": TERMINAL_TOKEN}
        with httpx.Client(trust_env=False, timeout=60) as client:
            have = client.get(f"{TERMINAL_URL}/subjects", params={"sid": session.id}, headers=headers).json().get("files")
            if have != digests:
                client.post(f"{TERMINAL_URL}/subjects", params={"sid": session.id}, headers=headers,
                            files=[("files", (name, path.read_bytes(), "application/pdf")) for name, path in files.items()]).raise_for_status()
    except Exception:
        logging.getLogger("verdict").warning("could not hand the subject PDFs to the terminal", exc_info=True)


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
    shell = ws.query_params.get("kind") == "shell"     # a plain shell in claude's working copy; it has no report to collect
    context = review_context(session)   # what claude in this terminal reviews; its report is only kept for that
    await ws.accept()
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        await ws.send_bytes(b"\r\n[terminal] not configured. Start the app with `make run`.\r\n")
        await ws.close()
        return
    url = (TERMINAL_URL.replace("http", "ws", 1) + f"/pty?repo={quote(session.repo.path)}"
           f"&cols={int(ws.query_params.get('cols', 80))}&rows={int(ws.query_params.get('rows', 24))}")
    url += f"&sid={session_id}" + ("&kind=shell" if shell else "")
    prompt_id = ws.query_params.get("prompt", "")
    if not shell and re.fullmatch(r"[A-Za-z0-9_-]{8,64}", prompt_id):
        url += f"&prompt={prompt_id}"
    await asyncio.get_running_loop().run_in_executor(None, push_subjects, session)     # (before the terminal starts, so it sees the PDFs at once)
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
                await loop.run_in_executor(None, collect_claude_review, session, context)
            except Exception:
                pass

    tasks = [asyncio.create_task(to_browser()), asyncio.create_task(to_terminal())] + ([] if shell else [asyncio.create_task(watch_for_report())])
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
            if not shell:
                await asyncio.shield(asyncio.get_running_loop().run_in_executor(None, collect_claude_review, session, context))
        except (Exception, asyncio.CancelledError):
            pass
        code = getattr(upstream, "close_code", None)
        try:
            await upstream.close()
        except Exception:
            pass
        try:
            await ws.close(code=code if code in (4410, 4411) else 1000)    # 4410: claude ended, 4411: opened in another tab
        except RuntimeError:
            pass


@app.post("/api/sessions/{session_id}/terminal/end")
def end_terminal(session_id: str) -> dict:
    """The claude tab was closed on purpose: take what claude saved, then stop it (it otherwise keeps running, so that a
    reload or a dropped connection does not lose the conversation)."""
    session = session_or_404(session_id)
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        return {"ended": False}
    collect_claude_review(session, review_context(session))
    try:
        import httpx

        with httpx.Client(trust_env=False, timeout=10) as client:
            response = client.post(f"{TERMINAL_URL}/pty/end", params={"sid": session_id}, headers={"x-terminal-token": TERMINAL_TOKEN})
        return {"ended": bool(response.json().get("ended"))}
    except Exception:
        return {"ended": False}


@app.post("/api/sessions/{session_id}/shell/end")
def end_shell(session_id: str) -> dict:
    """The shell tab was closed on purpose: stop it. (Claude and the working copy stay while claude is still running.)"""
    session_or_404(session_id)
    if not (TERMINAL_URL and TERMINAL_TOKEN):
        return {"ended": False}
    try:
        import httpx

        with httpx.Client(trust_env=False, timeout=10) as client:
            response = client.post(f"{TERMINAL_URL}/pty/end", params={"sid": session_id, "kind": "shell"}, headers={"x-terminal-token": TERMINAL_TOKEN})
        return {"ended": bool(response.json().get("ended"))}
    except Exception:
        return {"ended": False}


def review_prompt_for(session: Session) -> tuple[str, dict]:
    if not session.results or session.repo is None:
        raise HTTPException(400, "run the checks first")
    session.review_items = manual_items(session.results)        # claude answers by these numbers
    session.review_context = review_context(session)
    store.save(session)
    root = repo_dir(session)
    docker_files = find_docker_files(p.as_posix() for p in repo_mod.tracked_files(root)) if root else []
    live = terminal_status()["workdir"] == "live"               # claude works in the project folder itself: it is told so, and its report goes elsewhere
    return build_review_prompt(project=session.repo.name or session.repo.path, subjects=list(session.subjects),
                               lang=session.lang(), results=session.results, docker_files=docker_files,
                               subjects_dir=f"{TERMINAL_SUBJECTS_ROOT}/{session.id}", live=live,
                               report_dir=f"{TERMINAL_REPORTS_ROOT}/{session.id}" if live else None)


@app.get("/api/sessions/{session_id}/review-prompt")
def review_prompt(session_id: str) -> dict:
    """The review request for claude, built from what the checks did and did not cover."""
    text, stats = review_prompt_for(session_or_404(session_id))
    return {"text": text, **stats}


@app.get("/api/sessions/{session_id}/fix-prompt")
def fix_prompt(session_id: str) -> dict:
    """A prompt that asks an AI to fix what the review found. `text` is empty when there is nothing to fix."""
    session = session_or_404(session_id)
    if not session.results or session.repo is None:
        raise HTTPException(400, "run the checks first")
    text, stats = build_fix_prompt(project=session.repo.name or session.repo.path, subjects=list(session.subjects),
                                   lang=session.lang(), results=session.results, ai=session.ai, claude=session.claude)
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


# Earlier versions also saved claude's report into the clone under these names. Only verdict.md is written now.
OLD_REVIEW_FILES = ("claude-review.md", "claude-review-report.md")


def is_generated(path: Path) -> bool:
    """A regular file (not a link) that this app wrote: it starts with the verdict marker."""
    try:
        return not path.is_symlink() and path.is_file() and path.read_bytes()[:200].startswith(VERDICT_MARKER.encode())
    except OSError:
        return False


def write_verdict(session: Session) -> None:
    """Save the verdict, with claude's review merged into it, inside the reviewed repository. No separate review file is
    written, and one left by an earlier version is removed (never a file of the project's own)."""
    root = repo_dir(session)
    if root is not None:
        for name in OLD_REVIEW_FILES:
            if is_generated(root / name):
                (root / name).unlink(missing_ok=True)
    session.verdict_file = write_generated(session, ("verdict.md", "verdict-report.md"), verdict_text(session))
    if not session.verdict_file and repo_dir(session) is not None:
        session.message = "Could not save the verdict into the repository (no writable file name)."


# ------------------------------------------------------------------ running checks


def make_work_copy(session: Session, clone: Path) -> Path:
    """A disposable copy of the clone, where the checks build and run things. The clone itself is never built in,
    so it always shows exactly what was committed (no .o files or binaries left over from a previous run).
    The copy is a git repository too (its .git, without hooks), so git works in the sandbox."""
    work = WORKSPACE / session.id / "work"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(clone, work, symlinks=True,
                    ignore=lambda folder, names: ["hooks"] if Path(folder) == clone / ".git" else [])
    return work


def _run(session: Session) -> None:
    clone = repo_dir(session).resolve()
    work: Path | None = None

    def emit(result: CheckResult) -> None:
        with store.lock:
            session.results.append(result)

    try:
        work = make_work_copy(session, clone)
        subjects = refresh_subject_files(session)
        run_checks(Ctx(repo=work.resolve(), rules=session.rules(), lang=session.lang(),
                       sandbox=sandbox.with_env({"SUBJECTS_DIR": str(subjects)}) if sandbox else None), emit)
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
    if not any(s.kind == "subject" for s in session.subjects.values()):
        raise HTTPException(400, "add at least one subject PDF first")
    refresh_subject_rules(session)                      # (so a better parser applies at once, not only to subjects added from now on)
    refresh_context(session)
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
    session.review_context = review_context(session)
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
