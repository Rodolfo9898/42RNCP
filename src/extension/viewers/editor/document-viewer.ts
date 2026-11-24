import * as vscode from "vscode";

/** Text and markdown that are not a file (a report made on the spot), opened as documents. */
export class DocumentViewer {
  async showText(content: string, language: string, beside?: boolean): Promise<void> {
    const doc = await vscode.workspace.openTextDocument({ content, language });
    await vscode.window.showTextDocument(doc, { preview: false, viewColumn: beside ? vscode.ViewColumn.Beside : undefined });
  }

  /** Shown as the page, with its code one click away in the Markdown preview. */
  async showMarkdown(content: string): Promise<void> {
    const doc = await vscode.workspace.openTextDocument({ content, language: "markdown" });
    await vscode.window.showTextDocument(doc, { preview: false });
    await vscode.commands.executeCommand("markdown.showPreview", doc.uri).then(undefined, () => {});
  }

  register(): vscode.Disposable[] {
    return [vscode.commands.registerCommand("verdict.showText", (text: string, language: string) => this.showText(text, language))];
  }
}
