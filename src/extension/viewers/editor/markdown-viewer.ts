import * as vscode from "vscode";
import type { EditorTabs } from "./editor-tabs";

const MARKDOWN_PREVIEW = "vscode.markdown.preview.editor";

/** Markdown opens as the rendered page (VS Code's own preview, set as the default editor of *.md in settings.json). The title bar
 * has a button for the code and, in the code, one for the page. (VS Code's own "Show Source" button does not work with a
 * preview that is the default: it asks for the file again and is given the preview again.) */
export class MarkdownViewer {
  constructor(private readonly tabs: EditorTabs) {}

  /** The page and the code of the same file, one in place of the other. */
  code(): Thenable<unknown> {
    return vscode.commands.executeCommand("workbench.action.reopenTextEditor");
  }

  async page(uri?: unknown): Promise<void> {
    const target = uri instanceof vscode.Uri ? uri : vscode.window.activeTextEditor?.document.uri;
    if (!target) return;
    const tab = this.tabs.active();
    await vscode.commands.executeCommand("vscode.openWith", target, MARKDOWN_PREVIEW, vscode.window.tabGroups.activeTabGroup.viewColumn);
    await this.tabs.closeIfClean(tab, target);
  }

  register(): vscode.Disposable[] {
    return [
      vscode.commands.registerCommand("verdict.markdownCode", () => this.code()),
      vscode.commands.registerCommand("verdict.markdownPreview", (uri?: unknown) => this.page(uri)),
    ];
  }
}
