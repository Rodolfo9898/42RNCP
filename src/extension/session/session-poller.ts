import * as vscode from "vscode";
import type { SessionLoader } from "./session-loader";
import type { SessionState } from "./session-state";

/** While the app works (cloning, the checks, the AI review) the session is read again every second. When the work stops, the
 * `then` callbacks given to `start` run once: that is how a finished run opens verdict.md. */
export class SessionPoller implements vscode.Disposable {
  private timer: NodeJS.Timeout | null = null;
  private after: Array<() => void> = [];

  constructor(private readonly loader: SessionLoader, private readonly session: SessionState, private readonly everyMs = 1000) {}

  start(then?: () => void): void {
    if (then) this.after.push(then);
    if (!this.timer) this.timer = setInterval(() => void this.tick(), this.everyMs);
  }

  private async tick(): Promise<void> {
    try { await this.loader.refresh(); } catch { /* the next tick tries again */ }
    if (this.session.busy()) return;
    this.stop();
    const callbacks = this.after;
    this.after = [];
    callbacks.forEach((callback) => callback());
  }

  private stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  dispose(): void { this.stop(); }
}
