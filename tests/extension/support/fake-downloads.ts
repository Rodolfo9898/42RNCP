import type { DownloadState, DownloadSummary } from "../../../src/extension/api/types";
import type { FakeApp, Recorded } from "./fake-app";

/** The download service behind the fake app: a log that grows and a state, answered by the three routes of `library/downloads`. It is
 * running a download from the start; a test makes it go on (`say`) and end (`end`) while the extension follows it. */
export class FakeDownloads {
  state: DownloadState = "running";
  lines: string[] = [];
  summary: DownloadSummary | null = null;

  constructor(app: FakeApp) {
    app.on("POST library/downloads", { id: "d1", state: "running" }, 202)
      .on("GET library/downloads/current", (request: Recorded) => ({
        state: this.state, id: "d1", lines: this.lines.slice(Number(request.query.get("since"))), next: this.lines.length, summary: this.summary }))
      .on("DELETE library/downloads/current", () => ({ state: this.state }));
  }

  say(...lines: string[]): void { this.lines.push(...lines); }

  end(state: DownloadState, summary: DownloadSummary | null = null): void {
    this.state = state;
    this.summary = summary;
  }
}

export const aSummary = (extra: Partial<DownloadSummary> = {}): DownloadSummary =>
  ({ downloaded_subjects: 12, downloaded_artifacts: 30, existing: 5, failed: [], no_files: [], ...extra });
