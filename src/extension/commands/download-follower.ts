import * as vscode from "vscode";
import type { DownloadStatus } from "../api/types";
import type { VerdictApi } from "../api/verdict-api";
import type { ChannelLog } from "../output/channel-log";

type Notification = vscode.Progress<{ message?: string }>;

/** Follows the download the app is running: every couple of seconds it asks for the log lines it has not seen, writes each one in the
 * channel once, and ends with the last status the app gave. The notification's Cancel button asks the app to stop; the app stops
 * between two projects, so the following goes on until it says so. */
export class DownloadFollower {
  constructor(private readonly api: VerdictApi, private readonly log: ChannelLog, private readonly everyMs = 2000) {}

  async follow(): Promise<DownloadStatus> {
    this.log.show(true);
    return vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "Downloading subjects from the intra…", cancellable: true },
      async (progress, token) => {
        const cancel = token.onCancellationRequested(() => void this.stop());
        try { return await this.poll(progress); } finally { cancel.dispose(); }
      });
  }

  private async stop(): Promise<void> {
    this.log.line("Stopping after the project in progress…");
    try {
      await this.api.stopDownload();
    } catch (err) {
      this.log.line(`The download could not be stopped: ${(err as Error).message}`);
    }
  }

  /** Resolves with the status that is not "running" any more; rejects when the app cannot be asked (the download goes on in the app:
   * running the command again follows it). */
  private poll(progress: Notification): Promise<DownloadStatus> {
    return new Promise((resolve, reject) => {
      let next = 0;
      let asking = false;
      const ask = async (): Promise<void> => {
        if (asking) return;
        asking = true;
        try {
          const status = await this.api.download(next);
          next = status.next;
          for (const line of status.lines) this.log.line(line);
          if (status.lines.length) progress.report({ message: status.lines[status.lines.length - 1] });
          if (status.state !== "running") { clearInterval(timer); resolve(status); }
        } catch (err) {
          clearInterval(timer);
          reject(err);
        } finally {
          asking = false;
        }
      };
      const timer = setInterval(() => void ask(), this.everyMs);
      void ask();
    });
  }
}
