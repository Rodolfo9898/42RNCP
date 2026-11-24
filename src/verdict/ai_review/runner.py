"""One AI review, run in a thread: read the project, analyse it, assess the items the checks left to a human, publish."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from verdict.ai_review.jobs import AiJobs
from verdict.core.models import AIEvent, AIState
from verdict.documents.verdict_file import VerdictFile
from verdict.projects.folders import ProjectFolders
from verdict.reports import improve as improve_mod
from verdict.reports.report import summarize
from verdict.reviews import ai as ai_mod
from verdict.reviews.digest import Digest, build_digest, line_index
from verdict.sessions.store import Session, Store

MAX_STEPS = 120                                       # progress lines kept
MAX_MANUAL_ITEMS = 60


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AiProgress:
    """What the review is doing, as the person sees it (ignored once it was cancelled or replaced)."""

    def __init__(self, store: Store, session: Session, state: AIState) -> None:
        self.store, self.session, self.state = store, session, state

    def note(self, text: str) -> None:
        with self.store.lock:
            if self.session.ai is self.state and self.state.state == "running":
                self.state.step = text
                self.state.progress.append(AIEvent(at=now(), text=text))
                del self.state.progress[:-MAX_STEPS]


class AiReviewRun:
    def __init__(self, store: Store, folders: ProjectFolders, document: VerdictFile, jobs: AiJobs, session: Session,
                 state: AIState, job: ai_mod.Job) -> None:
        self.store, self.folders, self.document, self.jobs = store, folders, document, jobs
        self.session, self.state, self.job = session, state, job

    def current(self) -> bool:
        return self.session.ai is self.state and self.state.state == "running"

    def run(self) -> None:
        try:
            digest = self._digest()
            backend, usage = ai_mod.make_client(repo=self.session.repo.path), ai_mod.Usage()
            backend.job = self.job
            overview, improvements = self._analyse(backend, digest, usage)
            reviews = self._assess(backend, digest, usage)
            if self._publish(backend, digest, usage, overview, improvements, reviews):
                self.document.write(self.session)
        except ai_mod.Cancelled:
            pass                                      # the cancel route already recorded it
        except ai_mod.AIError as exc:
            self._fail(str(exc), f"Failed: {exc}")
        except Exception:
            logging.getLogger("verdict").exception("AI review failed")
            self._fail("Unexpected error during the AI review (see the server log).", None)
        finally:
            self.jobs.discard(self.session.id, self.job)
        self.store.save(self.session)

    def _digest(self) -> Digest:
        root = self.folders.of(self.session)
        limit = int(os.environ.get("LLM_MAX_CHARS") or (100_000 if ai_mod.provider() == "openai" else 150_000))
        if ai_mod.provider() == "claude-cli":
            digest = Digest(text="", lines=line_index(root))      # claude reads the files itself; this only validates citations
            self.job.notify(f"claude will explore {len(digest.lines)} files itself with read-only tools")
            return digest
        self.job.notify(f"Reading the repository (sending at most {limit:,} characters)")
        digest = build_digest(root, limit)
        cut = f"; {len(digest.truncated)} cut, {len(digest.omitted)} left out" if digest.truncated or digest.omitted else ""
        self.job.notify(f"Prepared {len(digest.included)} files, {len(digest.text):,} characters{cut}")
        return digest

    def _analyse(self, backend, digest: Digest, usage) -> tuple:
        known = [i.title for i in self.session.improvements if i.source == "static"]
        overview, improvements = ai_mod.analyze(backend, digest, subjects=list(self.session.subjects), summary=self._check_summary(),
                                                known_titles=known, usage=usage)
        self.job.notify(f"Overview ready; kept {len(improvements)} improvement idea(s) whose citations check out")
        return overview, improvements

    def _assess(self, backend, digest: Digest, usage) -> dict:
        manual: dict[str, str] = {}
        for r in self.session.results:
            if r.status == "manual" and r.rule_id and r.rule_id not in manual:
                manual[r.rule_id] = r.detail or r.title
        if not manual:
            return {}
        return ai_mod.review(backend, digest, list(manual.items())[:MAX_MANUAL_ITEMS], usage, subjects=list(self.session.subjects))

    def _publish(self, backend, digest: Digest, usage, overview, improvements, reviews) -> bool:
        s, state = self.session, self.state
        with self.store.lock:
            if not self.current():
                return False                          # cancelled or replaced while the last request was in flight: drop the result
            state.model = backend.model               # may differ from the configured one after a fallback
            state.overview, state.reviews = overview, reviews
            state.input_tokens, state.output_tokens = usage.input_tokens, usage.output_tokens
            state.not_fully_sent = digest.truncated + digest.omitted
            state.generated_at = now()
            s.improvements = sorted([i for i in s.improvements if i.source != "ai"] + improvements,
                                    key=lambda i: improve_mod.PRIORITY_ORDER[i.priority])
            state.progress.append(AIEvent(at=now(), text=f"Done: {len(reviews)} item(s) assessed with {backend.model}"))
            state.step, state.state, state.message = "", "done", ""
        return True

    def _fail(self, message: str, event: str | None) -> None:
        with self.store.lock:
            if self.current():
                self.state.state, self.state.message, self.state.step = "error", message, ""
                if event:
                    self.state.progress.append(AIEvent(at=now(), text=event))

    def _check_summary(self) -> str:
        counts = summarize(self.session.results)
        lines = [f"Result: {counts['overall']}",
                 "mandatory: " + ", ".join(f"{k} {v}" for k, v in counts["mandatory"].items()),
                 "bonus: " + ", ".join(f"{k} {v}" for k, v in counts["bonus"].items())]
        failed = [r.title + (f" ({r.detail[:100]})" if r.detail else "") for r in self.session.results if r.status == "fail"][:15]
        if failed:
            lines.append("Failed checks:\n" + "\n".join(f"- {t}" for t in failed))
        return "\n".join(lines)
