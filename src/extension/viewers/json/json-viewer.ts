import * as path from "node:path";
import * as vscode from "vscode";
import type { Configuration } from "../../settings/configuration";
import type { EditorTabs } from "../editor/editor-tabs";
import { SCHEME, fileOf, isJsonFile, readJson, viewUri } from "./json-files";
import type { PrettyJsonProvider } from "./json-provider";
import { MAX_BYTES, looksMinified, pretty } from "./pretty-json";

/** JSON saved on one line, or as long lines, opens as a pretty-printed view: read-only, shown with the JSON colours, and the file
 * on disk is never touched. A button opens the raw file, and a file that is shown raw has one to go back. */
export class JsonViewer {
  private readonly raw = new Set<string>();         // files shown raw on purpose (uri strings), until their tab is closed
  private readonly busy = new Set<string>();        // files being replaced by their pretty view

  constructor(private readonly config: Configuration, private readonly tabs: EditorTabs, private readonly provider: PrettyJsonProvider) {}

  /** A JSON file that was just opened and is hard to read: its tab becomes the pretty view, in the same place. */
  async prettify(tab: vscode.Tab): Promise<void> {
    const uri = this.tabs.textUri(tab);
    if (!this.config.prettyJsonOnOpen() || !uri || !isJsonFile(uri)) return;
    const key = uri.toString();
    if (this.raw.has(key) || this.busy.has(key)) return;
    this.busy.add(key);
    try {
      const text = await readJson(uri.fsPath);
      const here = () => tab.group.tabs.find((t) => this.tabs.textUri(t)?.toString() === key);    // (the tab may have been closed or edited meanwhile)
      if (text === null || !looksMinified(text) || !here() || here()?.isDirty) return;
      const view = await vscode.workspace.openTextDocument(viewUri(uri.fsPath));
      await vscode.window.showTextDocument(view, { viewColumn: tab.group.viewColumn, preview: tab.isPreview, preserveFocus: !tab.isActive });
      const still = here();
      if (still && !still.isDirty) await vscode.window.tabGroups.close(still);
    } catch {
      /* the file stays as it is */
    } finally {
      this.busy.delete(key);
    }
  }

  /** The raw file, as text, in place of the pretty view. */
  async openRaw(view?: unknown): Promise<void> {
    const target = view instanceof vscode.Uri ? view : vscode.window.activeTextEditor?.document.uri;
    const file = target && target.scheme === SCHEME ? fileOf(target) : null;
    if (!file) return;
    const uri = vscode.Uri.file(file);
    this.raw.add(uri.toString());
    const tab = this.tabs.active();
    await vscode.window.showTextDocument(uri, { viewColumn: tab?.group.viewColumn, preview: false });
    if (tab && tab.input instanceof vscode.TabInputText && tab.input.uri.scheme === SCHEME) await vscode.window.tabGroups.close(tab);
  }

  /** A JSON file as its pretty view, in place of the text (valid JSON only). */
  async openPretty(file?: unknown): Promise<void> {
    const target = file instanceof vscode.Uri ? file : vscode.window.activeTextEditor?.document.uri;
    if (!target || !isJsonFile(target)) return;
    const text = await readJson(target.fsPath);
    if (text === null || pretty(text) === null) {
      void vscode.window.showWarningMessage(`${path.basename(target.fsPath)} is not valid JSON, or is too big: it can only be shown as it is.`);
      return;
    }
    this.raw.delete(target.toString());
    const tab = this.tabs.active();
    const view = await vscode.workspace.openTextDocument(viewUri(target.fsPath));
    await vscode.window.showTextDocument(view, { viewColumn: tab?.group.viewColumn, preview: false });
    await this.tabs.closeIfClean(tab, target);
  }

  /** The "pretty" button is only offered on a JSON file that is hard to read. */
  offerPretty(): Thenable<unknown> {
    const doc = vscode.window.activeTextEditor?.document;
    const offer = !!doc && isJsonFile(doc.uri) && doc.getText().length <= MAX_BYTES && looksMinified(doc.getText());
    return vscode.commands.executeCommand("setContext", "verdict.jsonMinified", offer);
  }

  private forget(tab: vscode.Tab): void {
    const uri = this.tabs.textUri(tab);
    if (uri) this.raw.delete(uri.toString());
  }

  register(): vscode.Disposable[] {
    const disposables = [
      vscode.commands.registerCommand("verdict.jsonRaw", (view?: unknown) => this.openRaw(view)),
      vscode.commands.registerCommand("verdict.jsonPretty", (file?: unknown) => this.openPretty(file)),
      vscode.workspace.registerTextDocumentContentProvider(SCHEME, this.provider),
      vscode.window.tabGroups.onDidChangeTabs((e) => {
        e.opened.forEach((tab) => void this.prettify(tab));
        e.closed.forEach((tab) => this.forget(tab));
      }),
      vscode.workspace.onDidCloseTextDocument((doc) => { if (doc.uri.scheme === SCHEME) this.provider.unfollow(doc.uri); }),
      vscode.window.onDidChangeActiveTextEditor(() => this.offerPretty()),
      vscode.workspace.onDidSaveTextDocument(() => this.offerPretty()),
      this.provider,
    ];
    this.tabs.all().forEach((tab) => void this.prettify(tab));          // the tabs the editor restored when it opened
    void this.offerPretty();
    return disposables;
  }
}
