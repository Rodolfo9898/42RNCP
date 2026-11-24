import * as path from "node:path";
import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { ExistingFolder } from "../api/types";
import type { Logs } from "../output/channel-log";
import type { ProjectFolder } from "../session/project-folder";
import type { SessionState } from "../session/session-state";
import type { CommandGroup, CommandRegistry } from "./registry";

const PROJECTS_FOLDER_ITSELF = "(the projects folder itself)";

/** Which project is under review: one already in the projects folder, or a repository cloned into it. */
export class ProjectCommands implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly session: SessionState, private readonly folder: ProjectFolder, private readonly logs: Logs) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [commands.guarded("verdict.openProject", () => this.open()), commands.guarded("verdict.cloneProject", () => this.clone())];
  }

  async open(): Promise<void> {
    const { existing } = await this.api.projects();
    if (!existing.length) {
      const pick = await vscode.window.showInformationMessage(`There is no project in ${this.folder.projectsDir} yet.`, "Clone a Repository…");
      if (pick) await this.clone();
      return;
    }
    const choice = await vscode.window.showQuickPick(this.choices(existing),
      { title: "Review which project?", placeHolder: "A folder of the projects folder", matchOnDescription: true });
    if (!choice) return;
    this.session.set(await this.api.useExistingRepo(this.session.id, choice.label));
    await this.started();
  }

  /** The folders to pick from; the project of the file open in the editor (the deepest folder that holds it) comes first. */
  private choices(existing: ExistingFolder[]): vscode.QuickPickItem[] {
    const items = existing.map((f) => ({ label: f.path, description: f.git ? "" : "not a git repository" }));
    const active = vscode.window.activeTextEditor?.document.uri.fsPath;
    const here = active
      ? items.filter((i) => active.startsWith(path.join(this.folder.projectsDir, i.label) + path.sep)).sort((x, y) => y.label.length - x.label.length)[0]
      : undefined;
    if (!here) return items;
    return [{ ...here, description: ["the open file's project", here.description].filter(Boolean).join(" · ") }, ...items.filter((i) => i !== here)];
  }

  async clone(): Promise<void> {
    const url = await vscode.window.showInputBox({ title: "Clone a repository", prompt: "Its git URL (SSH, e.g. git@vogsphere…, or HTTPS)", ignoreFocusOut: true });
    if (!url) return;
    const { folders } = await this.api.projects();
    const destination = folders.length
      ? await vscode.window.showQuickPick([PROJECTS_FOLDER_ITSELF, ...folders], { title: "Clone it into which folder?" })
      : PROJECTS_FOLDER_ITSELF;
    if (destination === undefined) return;
    const name = await vscode.window.showInputBox({ title: "Name of the folder", prompt: "Empty: the repository's name", ignoreFocusOut: true });
    if (name === undefined) return;
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: `Cloning ${url}…` }, async () => {
      this.session.set(await this.api.cloneRepo(this.session.id, { url, name, destination: destination === PROJECTS_FOLDER_ITSELF ? "" : destination }));
    });
    await this.started();
  }

  /** The project is chosen: say so in the Output, and show it in the Explorer. */
  private async started(): Promise<void> {
    const repo = this.session.require().repo;
    this.logs.checks.line(`Project: ${repo?.path} @ ${repo?.commit}`);
    const dir = this.folder.dir();
    if (dir) await vscode.commands.executeCommand("revealInExplorer", vscode.Uri.file(dir)).then(undefined, () => {});
  }
}
