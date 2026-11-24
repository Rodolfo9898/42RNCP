import * as path from "node:path";
import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { ProjectFolder } from "../session/project-folder";
import type { SessionState } from "../session/session-state";
import type { CommandGroup, CommandRegistry } from "./registry";
import { libraryChoices } from "./subject-picker";
import type { LibraryChoice } from "./subject-picker";

/** The subjects of the review: PDFs of the library, PDFs uploaded into it, and taking one out. */
export class SubjectCommands implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly session: SessionState, private readonly folder: ProjectFolder) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [
      commands.guarded("verdict.addSubjects", () => this.add()),
      commands.guarded("verdict.uploadSubject", () => this.upload()),
      commands.guarded("verdict.removeSubject", (item?: { subject?: string }) => this.remove(item)),
    ];
  }

  async add(): Promise<void> {
    const lib = await this.api.library();
    if (!lib.items.length) {
      void vscode.window.showInformationMessage(`The library is empty: put PDFs in ${lib.tracks.map((t) => `samples/${t.id}/`).join(", ")}, or upload one.`);
      return;
    }
    const view = this.session.require();
    const have = new Set(view.subjects.map((s) => s.name));
    const name = view.repo?.name || "";
    const picks = await vscode.window.showQuickPick<LibraryChoice>(libraryChoices(lib, have, name),
      { canPickMany: true, title: "Add subjects", placeHolder: name ? `e.g. ${name}.pdf` : "Pick the subject PDFs", matchOnDescription: true });
    if (!picks) return;
    const paths = picks.flatMap((p) => (p.path && !have.has(p.label) ? [p.path] : []));
    if (paths.length) this.session.set(await this.api.addSubjects(this.session.id, paths));
  }

  /** The PDFs go into the library's folder of the track the person names, and from there into the review. */
  async upload(): Promise<void> {
    const files = await vscode.window.showOpenDialog({ canSelectMany: true, filters: { "Subject PDF": ["pdf"] }, title: "Upload subject PDFs",
      defaultUri: vscode.Uri.file(this.folder.dir() || this.folder.projectsDir) });
    if (!files || !files.length) return;
    const lib = await this.api.library();
    const track = await vscode.window.showQuickPick(lib.tracks.map((t) => ({ label: t.label, description: `samples/${t.id}/`, id: t.id })),
      { title: "Where does this subject belong?", placeHolder: "It is added to this review and kept in that library folder" });
    if (!track) return;
    const uploads = await Promise.all(files.map(async (f) => ({ name: path.basename(f.fsPath), bytes: await vscode.workspace.fs.readFile(f) })));
    const stored = await this.api.uploadSubjects(track.id, uploads);
    this.session.set(await this.api.addSubjects(this.session.id, stored.map((item) => item.path)));
  }

  async remove(item?: { subject?: string }): Promise<void> {
    if (item?.subject) this.session.set(await this.api.removeSubject(this.session.id, item.subject));
  }
}
