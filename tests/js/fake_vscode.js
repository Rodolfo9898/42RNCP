"use strict";

// Just enough of the `vscode` module for the Verdict extension to load and run in node: windows, tabs, documents, commands, messages.
// Everything the extension does to the editor is recorded in `calls`, so a test can say what the user would have seen.

const fs = require("fs");
const path = require("path");

class EventEmitter {
  constructor() { this.listeners = []; this.event = (fn) => { this.listeners.push(fn); return { dispose: () => { this.listeners = this.listeners.filter((l) => l !== fn); } }; }; }
  fire(value) { for (const fn of [...this.listeners]) fn(value); }
  dispose() { this.listeners = []; }
}

class Uri {
  constructor(scheme, p, query = "") { this.scheme = scheme; this.path = p; this.query = query; }
  static file(p) { return new Uri("file", p); }
  static from({ scheme, path: p, query }) { return new Uri(scheme, p, query || ""); }
  get fsPath() { return this.path; }
  toString() { return `${this.scheme}:${this.path}${this.query ? `?${this.query}` : ""}`; }
}

class TabInputText { constructor(uri) { this.uri = uri; } }
class TabInputCustom { constructor(uri, viewType) { this.uri = uri; this.viewType = viewType; } }
class ThemeIcon { constructor(id, color) { this.id = id; this.color = color; } }
class ThemeColor { constructor(id) { this.id = id; } }
class TreeItem { constructor(label, state) { this.label = label; this.collapsibleState = state; } }
class MarkdownString { appendText(t) { this.value = t; return this; } }
class Range { constructor(a, b, c, d) { this.start = { line: a, character: b }; this.end = { line: c, character: d }; } }

function create() {
  const calls = [];
  const settings = { "verdict.json.prettyOnOpen": true };
  const groups = [{ viewColumn: 1, tabs: [], isActive: true, get activeTab() { return this.tabs[this.tabs.length - 1]; } }];
  const documents = new Map();
  const handlers = {};
  const providers = {};
  const emitters = { tabs: new EventEmitter(), activeEditor: new EventEmitter(), saved: new EventEmitter(), closed: new EventEmitter() };
  let active = null;

  const record = (name) => (...args) => { calls.push([name, ...args]); return Promise.resolve(undefined); };
  const messages = { information: [], buttons: [], warning: [], error: [] };

  const tabGroups = {
    get all() { return groups; },
    get activeTabGroup() { return groups.find((g) => g.isActive) || groups[0]; },
    onDidChangeTabs: emitters.tabs.event,
    async close(tab) {
      const group = groups.find((g) => g.tabs.includes(tab));
      if (!group) return false;
      group.tabs.splice(group.tabs.indexOf(tab), 1);
      emitters.tabs.fire({ opened: [], closed: [tab], changed: [] });
      return true;
    },
  };

  const vscode = {
    EventEmitter, Uri, TabInputText, TabInputCustom, ThemeIcon, ThemeColor, TreeItem, MarkdownString, Range,
    StatusBarAlignment: { Left: 1 }, TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 }, ProgressLocation: { Notification: 15 },
    QuickPickItemKind: { Separator: -1 }, ViewColumn: { Beside: -2 },
    calls, messages, handlers, providers, groups, documents, settings, emitters,
    window: {
      tabGroups,
      get activeTextEditor() { return active; },
      onDidChangeActiveTextEditor: emitters.activeEditor.event,
      createOutputChannel: () => ({ appendLine: (l) => calls.push(["output", l]), show() {}, dispose() {} }),
      createStatusBarItem: () => ({ show() {}, dispose() {} }),
      registerTreeDataProvider: () => ({ dispose() {} }),
      // A modal question is answered with its first button, as if the person clicked it.
      showInformationMessage: (m, ...rest) => {
        messages.information.push(m);
        messages.buttons.push(...rest.filter((r) => typeof r === "string"));
        const modal = rest.find((r) => r && typeof r === "object" && r.modal);
        return Promise.resolve(modal ? rest.find((r) => typeof r === "string") : undefined);
      },
      showWarningMessage: (m) => { messages.warning.push(m); return Promise.resolve(undefined); },
      showErrorMessage: (m) => { messages.error.push(m); return Promise.resolve(undefined); },
      createTerminal: (o) => { calls.push(["terminal", o]); return { show() {} }; },
      async showTextDocument(doc, options) {
        const uri = doc.uri || doc;
        const real = doc.uri ? doc : await vscode.workspace.openTextDocument(uri);
        const group = groups.find((g) => g.viewColumn === (options && options.viewColumn)) || tabGroups.activeTabGroup;
        const tab = { input: new TabInputText(real.uri), group, isDirty: false, isPreview: !!(options && options.preview), isActive: !(options && options.preserveFocus) };
        group.tabs.push(tab);
        active = { document: real };
        calls.push(["showTextDocument", real.uri.toString(), options]);
        emitters.tabs.fire({ opened: [tab], closed: [], changed: [] });
        return active;
      },
    },
    workspace: {
      getConfiguration: (section) => ({ get: (key, fallback) => (`${section}.${key}` in settings ? settings[`${section}.${key}`] : fallback) }),
      registerTextDocumentContentProvider(scheme, provider) { providers[scheme] = provider; return { dispose() {} }; },
      async openTextDocument(arg) {
        const uri = arg instanceof Uri ? arg : Uri.file(arg.path);
        const provider = providers[uri.scheme];
        const text = provider ? await provider.provideTextDocumentContent(uri) : fs.readFileSync(uri.fsPath, "utf8");
        const doc = { uri, getText: () => text, languageId: "json" };
        documents.set(uri.toString(), doc);
        return doc;
      },
      onDidCloseTextDocument: emitters.closed.event,
      onDidSaveTextDocument: emitters.saved.event,
      saveAll: record("saveAll"),
      fs: { readFile: async (uri) => fs.readFileSync(uri.fsPath) },
    },
    commands: {
      registerCommand(id, fn) { handlers[id] = fn; return { dispose() {} }; },
      async executeCommand(id, ...args) {
        calls.push(["command", id, ...args]);
        if (handlers[id]) return handlers[id](...args);
        return undefined;
      },
    },
    env: { clipboard: { writeText: record("clipboard") } },
    // For the tests: a tab the user opened.
    openTab(file, extra = {}) {
      const uri = Uri.file(file);
      const group = groups[0];
      const tab = { input: new TabInputText(uri), group, isDirty: false, isPreview: false, isActive: true, ...extra };
      group.tabs.push(tab);
      active = { document: { uri, getText: () => fs.readFileSync(file, "utf8") } };
      emitters.tabs.fire({ opened: [tab], closed: [], changed: [] });
      return tab;
    },
    names: () => groups.flatMap((g) => g.tabs).map((t) => `${t.input.uri.scheme}:${path.basename(t.input.uri.path)}`),
  };
  return vscode;
}

module.exports = { create };
