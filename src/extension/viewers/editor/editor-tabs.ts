import * as vscode from "vscode";

/** The tabs of the editor, as the viewers need to look at them. */
export class EditorTabs {
  all(): vscode.Tab[] {
    return vscode.window.tabGroups.all.flatMap((group) => group.tabs);
  }

  /** The file a tab shows as text (null for any other kind of tab). */
  textUri(tab: vscode.Tab): vscode.Uri | null {
    return tab.input instanceof vscode.TabInputText ? tab.input.uri : null;
  }

  active(): vscode.Tab | undefined {
    return vscode.window.tabGroups.activeTabGroup.activeTab;
  }

  /** Is this file open in an editor already (as text or as the page)? */
  isOpen(file: string): boolean {
    return this.all().some((tab) => {
      const input = tab.input;
      return (input instanceof vscode.TabInputText || input instanceof vscode.TabInputCustom) && input.uri.fsPath === file;
    });
  }

  /** A tab that shows `uri` as text and has nothing unsaved is closed (it was replaced by another view of the same file). */
  async closeIfClean(tab: vscode.Tab | undefined, uri: vscode.Uri): Promise<void> {
    if (tab && !tab.isDirty && this.textUri(tab)?.toString() === uri.toString()) await vscode.window.tabGroups.close(tab);
  }
}
