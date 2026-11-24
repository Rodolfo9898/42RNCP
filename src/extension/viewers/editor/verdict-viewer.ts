import * as fs from "node:fs";
import * as vscode from "vscode";
import type { VerdictApi } from "../../api/verdict-api";
import type { ProjectFolder } from "../../session/project-folder";
import type { SessionState } from "../../session/session-state";
import type { DocumentViewer } from "./document-viewer";
import type { EditorTabs } from "./editor-tabs";

/** verdict.md as a page (markdown opens as the page; the button in its title bar shows the code). */
export class VerdictViewer {
  constructor(private readonly api: VerdictApi, private readonly session: SessionState, private readonly folder: ProjectFolder,
    private readonly tabs: EditorTabs, private readonly documents: DocumentViewer) {}

  /** `quiet`: it opens without taking the focus, and an editor that has it already is left as it is (VS Code reloads it when the file changes). */
  async open(quiet: boolean): Promise<void> {
    const view = this.session.require();
    if (!view.results.length) {
      void vscode.window.showInformationMessage("Run the checks first.");
      return;
    }
    const file = view.verdict_file ? this.folder.uri(view.verdict_file) : null;
    if (file && fs.existsSync(file.fsPath)) {
      if (quiet && this.tabs.isOpen(file.fsPath)) return;
      await vscode.commands.executeCommand("vscode.open", file, { preview: false, preserveFocus: quiet });
      return;
    }
    await this.documents.showMarkdown(await this.api.verdictMarkdown(view.id));
  }

  /** After a run: the new verdict.md is opened. */
  openAfterRun(): void {
    if (this.session.current?.results.length) this.open(true).catch(() => {});
  }
}
