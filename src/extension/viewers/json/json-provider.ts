import * as fs from "node:fs";
import * as vscode from "vscode";
import { fileOf, readJson } from "./json-files";
import { pretty } from "./pretty-json";

/** The content of the pretty views. A view follows its file: when the file changes on disk, the view is made again. */
export class PrettyJsonProvider implements vscode.TextDocumentContentProvider, vscode.Disposable {
  private readonly changed = new vscode.EventEmitter<vscode.Uri>();
  private readonly watching = new Map<string, string>();        // pretty view (uri string) -> the file it follows
  readonly onDidChange = this.changed.event;

  async provideTextDocumentContent(view: vscode.Uri): Promise<string> {
    const file = fileOf(view);
    if (!file) return "";
    this.follow(view, file);
    const text = await readJson(file);
    return text === null ? "// this file cannot be read, or is too big to be shown here\n" : (pretty(text) ?? text);
  }

  private follow(view: vscode.Uri, file: string): void {
    const key = view.toString();
    if (this.watching.has(key)) return;
    this.watching.set(key, file);
    fs.watchFile(file, { persistent: false, interval: 1500 }, (now, before) => {
      if (now.mtimeMs !== before.mtimeMs || now.size !== before.size) this.changed.fire(view);
    });
  }

  unfollow(view: vscode.Uri): void {
    const key = view.toString();
    const file = this.watching.get(key);
    if (file === undefined) return;
    this.watching.delete(key);
    fs.unwatchFile(file);
  }

  dispose(): void {
    for (const file of this.watching.values()) fs.unwatchFile(file);
    this.watching.clear();
    this.changed.dispose();
  }
}
