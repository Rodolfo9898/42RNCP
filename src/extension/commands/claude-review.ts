import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { Logs } from "../output/channel-log";
import { describeMerge } from "../report/merge-message";
import type { ProjectFolder } from "../session/project-folder";
import type { SessionLoader } from "../session/session-loader";
import type { SessionState } from "../session/session-state";
import type { VerdictViewer } from "../viewers/editor/verdict-viewer";
import type { CommandGroup, CommandRegistry } from "./registry";

/** claude as the reviewer: started in a VS Code terminal with the review prompt, and its saved report merged into verdict.md. */
export class ClaudeReview implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly session: SessionState, private readonly loader: SessionLoader,
    private readonly folder: ProjectFolder, private readonly logs: Logs, private readonly verdict: VerdictViewer) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [commands.guarded("verdict.mergeClaudeReview", () => this.merge())];
  }

  /** claude in a VS Code terminal, in the project folder, started with the review prompt; it saves its report outside the project. */
  async start(): Promise<void> {
    const project = this.session.require().repo?.path;
    const go = await vscode.window.showInformationMessage("Ask claude to review what the checks could not?", { modal: true,
      detail: `claude gets a prompt built from this run: what the scripts verified, and everything they could not judge. It works in ${project} itself, asks before running anything, and its decision sets the result once you merge its report.` }, "Run");
    if (!go) return;
    const sid = this.session.id;
    const { text } = await this.api.reviewPrompt(sid);
    const file = path.join(os.tmpdir(), `verdict-prompt-${sid}-${Date.now()}.txt`);
    fs.writeFileSync(file, text, { mode: 0o600 });
    const dir = this.folder.require();
    const terminal = vscode.window.createTerminal({ name: "claude: review", cwd: dir, iconPath: new vscode.ThemeIcon("sparkle"),
      shellPath: "python3", shellArgs: ["-m", "editor_launcher", "claude", "--session", sid, "--project", dir, "--prompt-file", file] });
    terminal.show();
    this.logs.ai.line(`claude started in the terminal "claude: review" with the review prompt (${text.length} characters).`);
    void vscode.window.showInformationMessage("claude's report goes into verdict.md by itself, each time it saves it.");
  }

  /** The report claude saved, forced into verdict.md whatever happened before (the pickup missed it, or it is from an earlier commit). */
  async merge(): Promise<void> {
    const answer = await this.api.claudeReview(this.session.id, true);
    await this.loader.refresh();
    if (answer.warning) void vscode.window.showWarningMessage(answer.warning);
    const message = describeMerge(answer);
    this.logs.ai.line(message);
    void vscode.window.showInformationMessage(message);
    await this.verdict.open(false);
  }
}
