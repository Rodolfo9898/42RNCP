// What the web app answers (the "Public REST API" of the app). Only the fields the extension reads; an answer carries more.

export interface Evidence { file: string; line?: number; snippet?: string }
export interface Source { pdf: string; page?: number }

export interface CheckResult {
  rule_id?: string;
  title: string;
  status: string;
  detail?: string;
  section?: string;
  by?: string;
  evidence?: Evidence[];
  log?: string;
  sources?: Source[];
}

export interface AiAssessment { assessment: string; by?: string; finding?: string; why_manual?: string }
export interface AiState {
  state: string;
  message?: string;
  progress?: { text: string }[];
  reviews?: Record<string, AiAssessment>;
}

export interface RepoInfo { path: string; name?: string; commit?: string; url?: string }
export interface SubjectRule { kind: string; title: string }
export interface Subject { name: string; kind: string; track?: string; lang?: string; pages?: number; rules: SubjectRule[] }
export interface Summary { overall?: string; decided_by?: string; reason?: string }

/** The view of a review session (`GET sessions/{id}`). */
export interface SessionView {
  id: string;
  state: string;
  message?: string;
  repo: RepoInfo | null;
  subjects: Subject[];
  results: CheckResult[];
  summary: Summary;
  ai: AiState;
  verdict_file?: string | null;
}

export interface LlmInfo { configured: boolean; model: string; provider: string; host: string }
export interface Health { llm: LlmInfo }

export interface Track { id: string; label: string }
export interface LibraryItem { path: string; name: string; track: string; size?: number }
export interface Library { tracks: Track[]; items: LibraryItem[] }

/** A subject of the intra that has no PDF in the library yet; `path` is where it will be filed. */
export interface MissingSubject { name: string; path: string; slug: string }
export interface TrackPlan { track: string; label: string; total: number; with_pdf: number; missing: MissingSubject[] }
/** `valid`: can the saved login to the intra be used; `reason` says why not. */
export interface IntraSession { valid: boolean; reason: string }
/** What `GET library/plan` says: what the intra has that the library does not, track by track. */
export interface LibraryPlan { session: IntraSession; tracks: TrackPlan[]; unknown: string[]; misplaced: number }

export interface DownloadRequest { tracks: string[] | null; projects: string[] | null; artifacts: boolean; children: boolean; force: boolean }
export type DownloadState = "idle" | "running" | "done" | "failed" | "cancelled";
export interface DownloadSummary { downloaded_subjects: number; downloaded_artifacts: number; existing: number; failed: string[]; no_files: string[] }
/** `GET library/downloads/current?since=n`: the log lines from the n-th on, and the `since` to ask next time. */
export interface DownloadStatus { state: DownloadState; id: string; lines: string[]; next: number; summary: DownloadSummary | null }

export interface Move { from: string; to: string }
/** What filing the PDFs and artifacts in the folders of their series does (or, as a dry run, would do). */
export interface Reorganization { dry_run: boolean; done: number; moves: Move[] }

export interface ExistingFolder { path: string; git: boolean }
/** `folders`: where a clone can go; `existing`: what can be reviewed where it is. */
export interface Projects { root: string; folders: string[]; existing: ExistingFolder[] }

export interface CloneRequest { url: string; name: string; destination: string }

/** What `PUT claude-review` says, forced or not. */
export interface MergeAnswer {
  new: boolean;
  written: boolean;
  stale: boolean;
  verdict_file: string | null;
  structured: boolean;
  assessed: number;
  total: number;
  problems: string[];
  source_name: string;
  warning: string;
}

export interface ReviewPrompt { text: string }
export interface FixPrompt { text: string; must_fix: number; look_at: number }
export interface ProgressAnswer { project: string; result: string; symbol: string; before: string | null; changed: boolean }

export interface EnvironmentTool { name: string; ok: boolean; required?: boolean; detail?: string }
export interface EnvironmentPart { available: boolean; error?: string; tools: EnvironmentTool[] }
export interface Environment { ready: boolean; sandbox?: EnvironmentPart; terminal?: EnvironmentPart }
