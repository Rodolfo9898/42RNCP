import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { Logs } from "../output/channel-log";
import type { SessionPoller } from "../session/session-poller";
import type { SessionState } from "../session/session-state";
import type { ClaudeReview } from "./claude-review";
import type { CommandGroup, CommandRegistry } from "./registry";

/** The AI review. Who reviews is the app's choice: claude in a terminal when it is set up for it, otherwise the AI behind the API
 * (the app's health says which); the source files only leave the computer for the API one, after a question. */
export class AiReview implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly session: SessionState, private readonly poller: SessionPoller,
    private readonly logs: Logs, private readonly claude: ClaudeReview) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [
      commands.guarded("verdict.aiReview", () => this.run()),
      vscode.commands.registerCommand("verdict.showAiLog", () => this.logs.ai.show()),
    ];
  }

  async run(): Promise<void> {
    const view = this.session.require();
    if (!view.results.length) {
      void vscode.window.showWarningMessage("Run the checks first: the AI is asked about what they could not judge.");
      return;
    }
    const { llm } = await this.api.health();
    if (llm.provider === "claude-cli") return this.claude.start();
    if (!llm.configured) {
      void vscode.window.showWarningMessage("No AI is configured: set ANTHROPIC_API_KEY, or LLM_BASE_URL + LLM_API_KEY + LLM_MODEL, in .env.");
      return;
    }
    const go = await vscode.window.showWarningMessage(`Send the source files of ${view.repo?.path} to ${llm.host} (${llm.model})?`,
      { modal: true, detail: "The student's code leaves this computer. Its answers count in the result." }, "Send and review");
    if (!go) return;
    this.session.set(await this.api.startAiReview(this.session.id));
    this.logs.ai.show(true);
    this.poller.start();
  }
}
