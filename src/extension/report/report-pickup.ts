import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { MergeAnswer } from "../api/types";
import type { Logs } from "../output/channel-log";
import type { SessionLoader } from "../session/session-loader";
import type { SessionState } from "../session/session-state";
import type { VerdictViewer } from "../viewers/editor/verdict-viewer";
import { describeMerge } from "./merge-message";
import type { ReportFile } from "./report-file";
import { ReportWatcher } from "./report-watcher";

/** Looks at claude's report every couple of seconds (a stat of one file) and has the app merge it into verdict.md each time it is
 * saved; then shows what changed, without taking the focus from the terminal claude is typing in. */
export class ReportPickup implements vscode.Disposable {
  private readonly watcher: ReportWatcher<MergeAnswer>;
  private timer: NodeJS.Timeout | null = null;

  constructor(private readonly api: VerdictApi, private readonly session: SessionState, private readonly loader: SessionLoader,
    private readonly file: ReportFile, private readonly logs: Logs, private readonly verdict: VerdictViewer, private readonly everyMs = 2000) {
    this.watcher = new ReportWatcher(
      () => (this.session.current ? this.file.signature(this.session.current.id) : Promise.resolve(null)),
      () => this.api.claudeReview(this.session.id, false),
      (answer) => void this.merged(answer));
  }

  start(): void {
    this.timer = setInterval(() => void this.watcher.tick(), this.everyMs);
  }

  /** claude saved its report (again) and the app answered: say what became of it. */
  private async merged(answer: MergeAnswer): Promise<void> {
    try {
      if (answer.stale) {
        this.logs.ai.line("claude's report is for an earlier run of the checks or another project, so it is not merged: ask claude again (AI Review).");
        return;
      }
      if (!answer.new && !answer.written) return;
      await this.loader.refresh();
      if (!answer.new) return;
      const message = describeMerge(answer);
      this.logs.ai.line(message);
      void vscode.window.showInformationMessage(message);
      await this.verdict.open(true);
    } catch (err) {
      this.logs.ai.line(`claude's report was merged, but the view could not be refreshed: ${(err as Error).message}`);
    }
  }

  dispose(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}
