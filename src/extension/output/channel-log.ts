import * as vscode from "vscode";

const stamp = (): string => new Date().toTimeString().slice(0, 8);

/** One Output channel; every line it is given carries the time. */
export class ChannelLog implements vscode.Disposable {
  constructor(private readonly channel: vscode.OutputChannel) {}

  line(text: string | undefined): void {
    if (text) this.channel.appendLine(`[${stamp()}] ${text}`);
  }

  /** A report of several lines: the first carries the time, the others follow as they are. */
  block(lines: string[]): void {
    if (!lines.length) return;
    this.line(lines[0]);
    for (const text of lines.slice(1)) this.channel.appendLine(text);
  }

  show(preserveFocus?: boolean): void { this.channel.show(preserveFocus); }

  dispose(): void { this.channel.dispose(); }
}

/** The three channels: what the checks do ("Verdict: Checks"), what the AI review does ("Verdict: AI review") and what happens to the
 * subjects of the library: the plan, the downloads, the filing ("Verdict: Subjects"). */
export interface Logs { checks: ChannelLog; ai: ChannelLog; subjects: ChannelLog }
