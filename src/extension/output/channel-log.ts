import * as vscode from "vscode";

const stamp = (): string => new Date().toTimeString().slice(0, 8);

/** One Output channel; every line it is given carries the time. */
export class ChannelLog implements vscode.Disposable {
  constructor(private readonly channel: vscode.OutputChannel) {}

  line(text: string | undefined): void {
    if (text) this.channel.appendLine(`[${stamp()}] ${text}`);
  }

  show(preserveFocus?: boolean): void { this.channel.show(preserveFocus); }

  dispose(): void { this.channel.dispose(); }
}

/** The two channels: what the checks do ("Verdict: Checks") and what the AI review does ("Verdict: AI review"). */
export interface Logs { checks: ChannelLog; ai: ChannelLog }
