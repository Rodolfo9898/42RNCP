import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { SessionState } from "../session/session-state";
import type { DocumentViewer } from "../viewers/editor/document-viewer";
import type { VerdictViewer } from "../viewers/editor/verdict-viewer";
import type { CommandGroup, CommandRegistry } from "./registry";

const SYMBOLS: Record<string, string> = { PASS: "✅", "PASS WITH ISSUES": "⚠️", FAIL: "❌" };

/** What a review gives: verdict.md, the prompt that fixes what it found, and the result in Progress.md. */
export class ResultCommands implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly session: SessionState, private readonly verdict: VerdictViewer,
    private readonly documents: DocumentViewer) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [
      commands.guarded("verdict.openVerdict", () => this.verdict.open(false)),
      commands.guarded("verdict.fixPrompt", () => this.fixPrompt()),
      commands.guarded("verdict.updateProgress", () => this.updateProgress()),
    ];
  }

  async fixPrompt(): Promise<void> {
    const prompt = await this.api.fixPrompt(this.session.id);
    if (!prompt.text) {
      void vscode.window.showInformationMessage("Nothing to fix: the review found nothing lacking.");
      return;
    }
    await this.documents.showText(prompt.text, "markdown");
    void vscode.window.showInformationMessage(`${prompt.must_fix} to fix, ${prompt.look_at} to look at. Paste it into claude in the project's folder (you can edit it first).`, "Copy")
      .then((copy) => copy && vscode.env.clipboard.writeText(prompt.text));
  }

  /** The result the verdict shows now goes into this project's row of Progress.md. Pressed on purpose, once the result is one you accept. */
  async updateProgress(): Promise<void> {
    const view = this.session.require();
    if (!view.repo) throw new Error("open a project first");
    if (!view.results.length) throw new Error("run the checks first: there is no result to record yet");
    const result = view.summary.overall;
    const symbol = result ? SYMBOLS[result] : undefined;
    if (!symbol) throw new Error(`there is no result to record yet (it says ${result || "nothing"})`);
    const name = view.repo.name || view.repo.path;
    const ok = await vscode.window.showInformationMessage(`${name}: ${result}. Record ${symbol} in Progress.md?`, { modal: true }, "Update Progress.md");
    if (ok !== "Update Progress.md") return;
    const done = await this.api.updateProgress(view.id);
    void vscode.window.showInformationMessage(done.changed
      ? `Progress.md: ${done.project} is now ${done.symbol} (${done.before === null ? "new row" : `was ${done.before || "empty"}`}).`
      : `Progress.md already says ${done.symbol} for ${done.project}.`);
  }
}
