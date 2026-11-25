import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { ChannelLog } from "../output/channel-log";
import type { CommandGroup, CommandRegistry } from "./registry";
import { missingSubjects, planMessage, planReport } from "./subject-plan-report";

const DOWNLOAD = "Download";

/** What the library lacks: the plan the app makes against the intra, written in the "Verdict: Subjects" channel and said in a line. */
export class SubjectPlanCommands implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly log: ChannelLog) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [commands.guarded("verdict.subjectsPlan", () => this.show())];
  }

  /** Something missing and a login that works: the line comes with the button that downloads it. Without the login, downloading would be refused. */
  async show(): Promise<void> {
    const plan = await this.api.libraryPlan(true);
    this.log.block(planReport(plan));
    this.log.show(true);
    const message = planMessage(plan);
    if (!missingSubjects(plan)) {
      void vscode.window.showInformationMessage(message);
    } else if (!plan.session.valid) {
      void vscode.window.showWarningMessage(message);
    } else if (await vscode.window.showInformationMessage(message, DOWNLOAD) === DOWNLOAD) {
      await vscode.commands.executeCommand("verdict.subjectsDownload");
    }
  }
}
