import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { Logs } from "../output/channel-log";
import type { SessionLoader } from "../session/session-loader";
import type { SessionPoller } from "../session/session-poller";
import type { SessionState } from "../session/session-state";
import type { VerdictViewer } from "../viewers/editor/verdict-viewer";
import type { ProjectCommands } from "./project-commands";
import type { CommandGroup, CommandRegistry } from "./registry";
import type { SubjectCommands } from "./subject-commands";

/** Running the checks, and reading the session again. */
export class CheckCommands implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly session: SessionState, private readonly loader: SessionLoader,
    private readonly poller: SessionPoller, private readonly logs: Logs, private readonly project: ProjectCommands,
    private readonly subjects: SubjectCommands, private readonly verdict: VerdictViewer) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [commands.guarded("verdict.runChecks", () => this.run()), commands.guarded("verdict.refresh", () => this.refresh())];
  }

  private readonly hasSubject = (): boolean => this.session.require().subjects.some((s) => s.kind === "subject");

  /** A run needs a project and a subject: whichever is missing is asked for first. When the checks end, the new verdict.md is opened. */
  async run(): Promise<void> {
    if (!this.session.require().repo) { await this.project.open(); if (!this.session.require().repo) return; }
    if (!this.hasSubject()) { await this.subjects.add(); if (!this.hasSubject()) return; }
    await vscode.workspace.saveAll(false);
    this.logs.checks.line("— a new run starts from nothing —");
    this.session.set(await this.api.startRun(this.session.id));
    this.logs.checks.show(true);
    this.poller.start(() => this.verdict.openAfterRun());
  }

  async refresh(): Promise<void> {
    await this.loader.refresh();
    if (this.session.busy()) this.poller.start();
  }
}
