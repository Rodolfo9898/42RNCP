import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { DocumentViewer } from "../viewers/editor/document-viewer";
import { environmentMarkdown } from "./environment-report";
import type { CommandGroup, CommandRegistry } from "./registry";

/** Can the sandbox (where the checks run) and the terminal (where claude works) really build and run things? */
export class EnvironmentCommands implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly documents: DocumentViewer) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [commands.guarded("verdict.checkEnvironment", () => this.check())];
  }

  async check(): Promise<void> {
    const mode = await vscode.window.showQuickPick([
      { label: "Quick", description: "tool versions, C and C++ through make, the Docker daemon", deep: false },
      { label: "Full", description: "also builds and runs a tiny Dockerfile (downloads a base image: needs internet)", deep: true }],
      { title: "Check the Environment", placeHolder: "Where the checks run (sandbox) and where claude works (terminal)" });
    if (!mode) return;
    const env = await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "Checking the environment…" },
      () => this.api.environment(mode.deep));
    await this.documents.showMarkdown(environmentMarkdown(env));
  }
}
