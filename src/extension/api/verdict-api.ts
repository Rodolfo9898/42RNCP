import type { ApiClient } from "./client";
import type {
  CloneRequest, DownloadRequest, DownloadState, DownloadStatus, Environment, FixPrompt, Health, Library, LibraryItem, LibraryPlan, MergeAnswer,
  ProgressAnswer, Projects, Reorganization, ReviewPrompt, SessionView,
} from "./types";

export interface UploadFile { name: string; bytes: Uint8Array }

/** The routes of the web app, one method each and typed (Facade over the client): nothing else in the extension builds a URL. */
export class VerdictApi {
  constructor(private readonly client: ApiClient) {}

  health(): Promise<Health> { return this.client.json("health"); }
  environment(deep: boolean): Promise<Environment> { return this.client.json(`environment${deep ? "?deep=true" : ""}`); }
  library(): Promise<Library> { return this.client.json("library"); }
  projects(): Promise<Projects> { return this.client.json("projects"); }

  createSession(): Promise<SessionView> { return this.client.json("sessions", { method: "POST" }); }
  session(sid: string): Promise<SessionView> { return this.client.json(this.of(sid)); }

  /** PDFs into the library's folder of a track; the answer says where each one went (to add to a review with `addSubjects`). */
  async uploadSubjects(track: string, files: UploadFile[]): Promise<LibraryItem[]> {
    const form = new FormData();
    for (const file of files) form.append("files", new Blob([file.bytes], { type: "application/pdf" }), file.name);
    const answer = await this.client.json<{ items: LibraryItem[] }>(`library/${encodeURIComponent(track)}/subjects`, { method: "POST", form });
    return answer.items;
  }

  addSubjects(sid: string, paths: string[]): Promise<SessionView> {
    return this.client.json(`${this.of(sid)}/subjects`, { method: "POST", body: { paths } });
  }

  removeSubject(sid: string, name: string): Promise<SessionView> {
    return this.client.json(`${this.of(sid)}/subjects/${encodeURIComponent(name)}`, { method: "DELETE" });
  }

  pagePng(sid: string, name: string, page: number): Promise<Buffer> {
    return this.client.bytes(`${this.of(sid)}/subjects/${encodeURIComponent(name)}/pages/${page}.png`);
  }

  cloneRepo(sid: string, request: CloneRequest): Promise<SessionView> {
    return this.client.json(`${this.of(sid)}/repo`, { method: "PUT", body: { kind: "clone", ...request } });
  }

  useExistingRepo(sid: string, path: string): Promise<SessionView> {
    return this.client.json(`${this.of(sid)}/repo`, { method: "PUT", body: { kind: "existing", path } });
  }

  startRun(sid: string): Promise<SessionView> { return this.client.json(`${this.of(sid)}/runs`, { method: "POST" }); }
  startAiReview(sid: string): Promise<SessionView> { return this.client.json(`${this.of(sid)}/ai-review`, { method: "POST" }); }

  /** Claude's saved report into the session and verdict.md. `force`: whatever happened before; without it only a report this review asked for. */
  claudeReview(sid: string, force: boolean): Promise<MergeAnswer> {
    return this.client.json(`${this.of(sid)}/claude-review`, { method: "PUT", body: { force } });
  }

  reviewPrompt(sid: string): Promise<ReviewPrompt> { return this.client.json(`${this.of(sid)}/prompts/review`); }
  fixPrompt(sid: string): Promise<FixPrompt> { return this.client.json(`${this.of(sid)}/prompts/fix`); }
  updateProgress(sid: string): Promise<ProgressAnswer> { return this.client.json(`${this.of(sid)}/progress`, { method: "PUT" }); }
  verdictMarkdown(sid: string): Promise<string> { return this.client.text(`${this.of(sid)}/verdict.md`); }

  /** What the intra has that the library does not: all the tracks, or only these; `children`: the projects inside a piscine or a series too. */
  libraryPlan(children: boolean, tracks: string[] = []): Promise<LibraryPlan> {
    const query = new URLSearchParams([...tracks.map((track): [string, string] => ["track", track]), ["children", String(children)]]);
    return this.client.json(`library/plan?${query}`);
  }

  /** Starts the one download the service runs at a time (409 when it is busy); follow it with `download`. */
  startDownload(request: DownloadRequest): Promise<{ id: string; state: DownloadState }> {
    return this.client.json("library/downloads", { method: "POST", body: request });
  }

  /** The download now (or the last one): its state, and the log lines from the `since`-th on. */
  download(since: number): Promise<DownloadStatus> { return this.client.json(`library/downloads/current?since=${since}`); }
  stopDownload(): Promise<{ state: DownloadState }> { return this.client.json("library/downloads/current", { method: "DELETE" }); }

  /** Files the PDFs and artifacts that are on disk in the folders of their series; `dryRun`: only says what it would move. */
  reorganize(dryRun: boolean): Promise<Reorganization> {
    return this.client.json("library/reorganizations", { method: "POST", body: { dry_run: dryRun } });
  }

  private of(sid: string): string { return `sessions/${encodeURIComponent(sid)}`; }
}
