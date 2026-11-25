import * as vscode from "vscode";
import { ApiError } from "../api/client";
import type { DownloadRequest, DownloadStatus } from "../api/types";
import type { VerdictApi } from "../api/verdict-api";
import type { ChannelLog } from "../output/channel-log";
import { askDownload } from "./download-questions";
import type { DownloadFollower } from "./download-follower";
import { downloadMessage, summaryLines } from "./download-summary";
import type { CommandGroup, CommandRegistry } from "./registry";

/** Downloading the subject PDFs from the intra into the library. The app does the work (with a login made once on the person's own
 * computer); this asks what to download, and follows it in a notification and the "Verdict: Subjects" channel. */
export class SubjectDownloadCommands implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly follower: DownloadFollower, private readonly log: ChannelLog) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [commands.guarded("verdict.subjectsDownload", () => this.run())];
  }

  async run(): Promise<void> {
    const request = await askDownload();
    if (!request) return;
    await this.start(request);
    this.conclude(await this.follower.follow());
  }

  /** The app refuses a login that cannot be used (400) in words the person can act on: those reach the person as they are. One download
   * runs at a time (409): the one that runs is followed instead. */
  private async start(request: DownloadRequest): Promise<void> {
    try {
      await this.api.startDownload(request);
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 409) throw err;
      void vscode.window.showInformationMessage("A download is already running: following it.");
    }
  }

  private conclude(status: DownloadStatus): void {
    if (status.summary) this.log.block(summaryLines(status.summary));
    if (status.state === "failed") throw new Error("the download failed: see the Verdict: Subjects output");
    void vscode.window.showInformationMessage(downloadMessage(status));
  }
}
