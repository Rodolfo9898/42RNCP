// Just enough of the `vscode` module for the Verdict extension to load and run in node: windows, tabs, documents, commands, messages,
// pickers. Everything the extension does to the editor is recorded in `calls`, so a test can say what the person would have seen.
// It is typed as a partial of the real API (cast where the real signatures are wider than what the extension uses).

import * as fs from "node:fs";
import * as path from "node:path";
import type * as vscode from "vscode";
import { EventEmitter, MarkdownString, Range, TabInputCustom, TabInputText, ThemeColor, ThemeIcon, TreeItem, Uri } from "./fake-classes";

export type Call = [string, ...unknown[]];
type Handler = (...args: never[]) => unknown;

export interface FakeTab { input: unknown; group: FakeGroup; isDirty: boolean; isPreview: boolean; isActive: boolean }
export interface FakeGroup { viewColumn: number; tabs: FakeTab[]; isActive: boolean; readonly activeTab: FakeTab | undefined }
export interface FakeDocument { uri: Uri; getText(): string; languageId: string }
export interface FakeStatusItem { text?: string; tooltip?: string; command?: string; name?: string; shown: boolean; show(): void; dispose(): void }
interface ShowOptions { viewColumn?: number; preview?: boolean; preserveFocus?: boolean }

/** What a test scripts: the answers of the pickers and dialogs the person would have answered (undefined: dismissed). */
export interface Answers {
  /** A modal question is answered with its first button (as if the person clicked it) unless this is false. */
  confirm?: boolean;
  /** The button the person presses in a message that is not modal (none by default). */
  pressed?: string;
  quickPick?: (items: unknown, options: unknown) => unknown;
  inputBox?: (options: { title?: string }) => string | undefined;
  openDialog?: (options: unknown) => Uri[] | undefined;
}

/** A tab with a web page inside (the PDF viewer): what the page was given, what it said back, and whether the person closed it. */
export class FakePanel {
  disposed = false;
  revealed = 0;
  posted: unknown[] = [];
  readonly webview = {
    html: "",
    postMessage: (message: unknown): Promise<boolean> => { this.posted.push(message); return Promise.resolve(true); },
    onDidReceiveMessage: (fn: (message: unknown) => unknown): { dispose(): void } => { this.listeners.push(fn); return { dispose() {} }; },
  };
  private readonly listeners: Array<(message: unknown) => unknown> = [];
  private readonly disposers: Array<() => void> = [];

  constructor(readonly viewType: string, readonly title: string, readonly column: unknown, readonly options: unknown) {}

  reveal(): void { this.revealed++; }
  onDidDispose(fn: () => void): { dispose(): void } { this.disposers.push(fn); return { dispose() {} }; }
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.disposers.forEach((fn) => fn());
  }
  /** For the tests: the page says something to the extension. */
  say(message: unknown): Promise<unknown[]> { return Promise.all(this.listeners.map((fn) => fn(message))); }
}

export class FakeEditor {
  readonly calls: Call[] = [];
  readonly messages = { information: [] as string[], buttons: [] as string[], warning: [] as string[], error: [] as string[] };
  readonly handlers: Record<string, Handler> = {};
  readonly providers: Record<string, vscode.TextDocumentContentProvider> = {};
  readonly trees: Record<string, vscode.TreeDataProvider<unknown>> = {};
  readonly documents = new Map<string, FakeDocument>();
  readonly settings: Record<string, unknown> = {};
  readonly panels: FakePanel[] = [];
  readonly statusItems: FakeStatusItem[] = [];
  readonly answers: Answers = {};
  /** Files the extension reads through the editor (workspace.fs), by path; any other path is read from the disk. */
  readonly files = new Map<string, Uint8Array>();
  readonly group: FakeGroup = { viewColumn: 1, tabs: [], isActive: true, get activeTab() { return this.tabs[this.tabs.length - 1]; } };
  readonly groups = [this.group];
  readonly tabsChanged = new EventEmitter<{ opened: FakeTab[]; closed: FakeTab[]; changed: FakeTab[] }>();
  private readonly emitters = [this.tabsChanged, new EventEmitter<unknown>(), new EventEmitter<unknown>(), new EventEmitter<unknown>()];
  private active: { document: FakeDocument } | null = null;
  private untitled = 0;
  /** What `require("vscode")` gives the extension. */
  readonly api: typeof vscode;

  constructor() {
    this.api = this.buildApi();
    this.reset();
  }

  /** For the tests: a tab the person opened. */
  openTab(file: string, extra: Partial<FakeTab> = {}): FakeTab {
    const uri = Uri.file(file);
    const tab: FakeTab = { input: new TabInputText(uri), group: this.group, isDirty: false, isPreview: false, isActive: true, ...extra };
    this.group.tabs.push(tab);
    this.active = { document: { uri, getText: () => fs.readFileSync(file, "utf8"), languageId: "json" } };
    this.tabsChanged.fire({ opened: [tab], closed: [], changed: [] });
    return tab;
  }

  readonly closeTab = async (tab: FakeTab): Promise<boolean> => {
    const owner = this.groups.find((g) => g.tabs.includes(tab));
    if (!owner) return false;
    owner.tabs.splice(owner.tabs.indexOf(tab), 1);
    this.tabsChanged.fire({ opened: [], closed: [tab], changed: [] });
    return true;
  };

  names(): string[] {
    return this.groups.flatMap((g) => g.tabs).map((t) => `${(t.input as TabInputText).uri.scheme}:${path.basename((t.input as TabInputText).uri.path)}`);
  }

  /** The person runs a command (a menu, the palette, a click on a row). */
  readonly run = async (id: string, ...args: unknown[]): Promise<unknown> => {
    this.calls.push(["command", id, ...args]);
    const handler = this.handlers[id];
    return handler ? (handler as (...a: unknown[]) => unknown)(...args) : undefined;
  };

  /** Back to an editor with nothing open and nothing said. */
  reset(): void {
    this.calls.length = 0; this.panels.length = 0; this.statusItems.length = 0; this.documents.clear(); this.files.clear();
    this.group.tabs.length = 0; this.active = null; this.untitled = 0;
    for (const list of Object.values(this.messages)) list.length = 0;
    for (const table of [this.handlers, this.providers, this.trees, this.answers, this.settings] as Array<Record<string, unknown>>) {
      for (const key of Object.keys(table)) delete table[key];
    }
    this.emitters.forEach((emitter) => emitter.dispose());
    this.settings["verdict.json.prettyOnOpen"] = true;
  }

  private buildApi(): typeof vscode {
    const api: Partial<typeof vscode> = {
      EventEmitter: EventEmitter as never, Uri: Uri as never, TabInputText: TabInputText as never, TabInputCustom: TabInputCustom as never,
      ThemeIcon: ThemeIcon as never, ThemeColor: ThemeColor as never, TreeItem: TreeItem as never, MarkdownString: MarkdownString as never, Range: Range as never,
      StatusBarAlignment: { Left: 1 } as never, TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 } as never,
      ProgressLocation: { Notification: 15 } as never, QuickPickItemKind: { Separator: -1 } as never, ViewColumn: { Active: -1, Beside: -2 } as never,
      window: Object.assign(this.windowParts(), this.messagesAndPickers()) as typeof vscode.window,     // (not a spread: the parts have getters)
      workspace: this.workspace(),
      commands: { registerCommand: (id: string, fn: Handler) => { this.handlers[id] = fn; return { dispose() {} }; }, executeCommand: this.run } as never,
      env: { clipboard: { writeText: this.record("clipboard") } } as never,
    };
    return api as typeof vscode;
  }

  private record(name: string): (...args: unknown[]) => Promise<undefined> {
    return (...args) => { this.calls.push([name, ...args]); return Promise.resolve(undefined); };
  }

  // What the person is shown, and what they answer (see Answers).
  private messagesAndPickers(): Partial<typeof vscode.window> {
    const { calls, messages, answers } = this;
    return {
      showInformationMessage: this.message(messages.information) as never,
      showWarningMessage: this.message(messages.warning) as never,
      showErrorMessage: ((m: string) => { messages.error.push(m); return Promise.resolve(undefined); }) as never,
      showQuickPick: ((items: unknown, options: unknown) => { calls.push(["quickPick", items, options]); return Promise.resolve(answers.quickPick?.(items, options)); }) as never,
      showInputBox: ((options: { title?: string }) => { calls.push(["inputBox", options]); return Promise.resolve(answers.inputBox?.(options)); }) as never,
      showOpenDialog: ((options: unknown) => { calls.push(["openDialog", options]); return Promise.resolve(answers.openDialog?.(options)); }) as never,
      withProgress: ((options: unknown, task: (progress: unknown) => unknown) => { calls.push(["progress", options]); return Promise.resolve(task({ report() {} })); }) as never,
    };
  }

  /** A message shown to the person; `shown` keeps what it said, and the answer is the button pressed, if any. */
  private message(shown: string[]): (message: string, ...rest: unknown[]) => Promise<string | undefined> {
    return (message, ...rest) => {
      shown.push(message);
      const buttons = rest.filter((r): r is string => typeof r === "string");
      if (shown === this.messages.information) this.messages.buttons.push(...buttons);
      const modal = rest.some((r) => !!r && typeof r === "object" && (r as { modal?: boolean }).modal);
      const pressed = this.answers.pressed;
      if (pressed !== undefined && buttons.includes(pressed)) return Promise.resolve(pressed);
      return Promise.resolve(modal && this.answers.confirm !== false ? buttons[0] : undefined);
    };
  }

  private windowParts(): Partial<typeof vscode.window> {
    const self = this;
    const [, activeEditor] = this.emitters;
    return {
      tabGroups: { get all() { return self.groups; }, get activeTabGroup() { return self.group; }, onDidChangeTabs: this.tabsChanged.event, close: this.closeTab } as unknown as typeof vscode.window.tabGroups,
      get activeTextEditor() { return self.active as unknown as vscode.TextEditor; },
      onDidChangeActiveTextEditor: activeEditor.event as never,
      createOutputChannel: ((name: string) => ({ appendLine: (l: string) => this.calls.push(["output", l, name]), show: (preserveFocus?: boolean) => this.calls.push(["show", name, preserveFocus]), dispose() {} })) as never,
      createStatusBarItem: (() => {
        const item: FakeStatusItem = { shown: false, show() { item.shown = true; }, dispose() {} };
        this.statusItems.push(item);
        return item;
      }) as never,
      registerTreeDataProvider: ((id: string, provider: vscode.TreeDataProvider<unknown>) => { this.trees[id] = provider; return { dispose() {} }; }) as never,
      createWebviewPanel: ((...args: ConstructorParameters<typeof FakePanel>) => { const panel = new FakePanel(...args); this.panels.push(panel); return panel; }) as never,
      createTerminal: ((options: unknown) => { this.calls.push(["terminal", options]); return { show() {} }; }) as never,
      showTextDocument: this.showDocument as never,
    };
  }

  private workspace(): typeof vscode.workspace {
    const [, , saved, closed] = this.emitters;
    const workspace: Partial<typeof vscode.workspace> = {
      getConfiguration: ((section: string) => ({ get: (key: string, fallback: unknown) => (`${section}.${key}` in this.settings ? this.settings[`${section}.${key}`] : fallback) })) as never,
      registerTextDocumentContentProvider: ((scheme: string, provider: vscode.TextDocumentContentProvider) => { this.providers[scheme] = provider; return { dispose() {} }; }) as never,
      openTextDocument: this.openDocument as never,
      onDidCloseTextDocument: closed.event as never,
      onDidSaveTextDocument: saved.event as never,
      saveAll: this.record("saveAll") as never,
      fs: { readFile: async (uri: Uri) => this.files.get(uri.fsPath) ?? fs.readFileSync(uri.fsPath) } as never,
    };
    return workspace as typeof vscode.workspace;
  }

  private readonly openDocument = async (arg: Uri | { content: string; language?: string }): Promise<FakeDocument> => {
    if (!(arg instanceof Uri)) {
      const doc: FakeDocument = { uri: Uri.from({ scheme: "untitled", path: `Untitled-${++this.untitled}` }), getText: () => arg.content, languageId: arg.language || "plaintext" };
      this.documents.set(doc.uri.toString(), doc);
      return doc;
    }
    const provider = this.providers[arg.scheme];
    const text = provider ? await provider.provideTextDocumentContent(arg as unknown as vscode.Uri, undefined as never) : fs.readFileSync(arg.fsPath, "utf8");
    const doc: FakeDocument = { uri: arg, getText: () => text as string, languageId: "json" };
    this.documents.set(arg.toString(), doc);
    return doc;
  };

  private readonly showDocument = async (arg: FakeDocument | Uri, options?: ShowOptions): Promise<{ document: FakeDocument }> => {
    const doc = arg instanceof Uri ? await this.openDocument(arg) : arg;
    const target = this.groups.find((g) => g.viewColumn === options?.viewColumn) || this.group;
    const tab: FakeTab = { input: new TabInputText(doc.uri), group: target, isDirty: false, isPreview: !!options?.preview, isActive: !options?.preserveFocus };
    target.tabs.push(tab);
    this.active = { document: doc };
    this.calls.push(["showTextDocument", doc.uri.toString(), options]);
    this.tabsChanged.fire({ opened: [tab], closed: [], changed: [] });
    return this.active;
  };
}
