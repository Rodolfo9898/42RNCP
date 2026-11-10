"use strict";

// How files are shown in the editor.
//  - Markdown opens as the rendered page (VS Code's own preview, set as the default editor of *.md in settings.json). The title bar
//    has a button for the code and, in the code, one for the page. (VS Code's own "Show Source" button does not work with a
//    preview that is the default: it asks for the file again and is given the preview again.)
//  - JSON saved on one line, or as long lines, opens as a pretty-printed view: read-only, shown with the JSON colours, and the file
//    on disk is never touched. A button opens the raw file, and a file that is shown raw has one to go back.
// The pretty-printing itself is json.js; this is the editor side of it.

const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
const json = require("./json");

const SCHEME = "verdict-json";
const MARKDOWN_PREVIEW = "vscode.markdown.preview.editor";

const raw = new Set();              // files shown raw on purpose (uri strings), until their tab is closed
const busy = new Set();             // files being replaced by their pretty view
const watching = new Map();         // pretty view (uri string) -> the file it follows
const changed = new vscode.EventEmitter();

const isJsonFile = (uri) => uri.scheme === "file" && /\.json$/i.test(uri.path);
const enabled = () => vscode.workspace.getConfiguration("verdict").get("json.prettyOnOpen", true);

async function readJson(file) {
  try {
    if ((await fs.promises.stat(file)).size > json.MAX_BYTES) return null;
    return await fs.promises.readFile(file, "utf8");
  } catch {
    return null;
  }
}

// The address of the pretty view of a file: its name says it is the pretty one, its query says which file it follows.
function viewUri(file) {
  const name = path.basename(file).replace(/\.json$/i, "");
  return vscode.Uri.from({ scheme: SCHEME, path: `${path.dirname(file)}/${name} (pretty).json`, query: new URLSearchParams({ file }).toString() });
}

function fileOf(view) {
  const file = new URLSearchParams(view.query).get("file");
  return file && path.isAbsolute(file) && /\.json$/i.test(file) ? file : null;
}

class PrettyJson {
  constructor() { this.onDidChange = changed.event; }

  async provideTextDocumentContent(view) {
    const file = fileOf(view);
    if (!file) return "";
    follow(view, file);
    const text = await readJson(file);
    return text === null ? "// this file cannot be read, or is too big to be shown here\n" : (json.pretty(text) ?? text);
  }
}

// A pretty view follows its file: when the file changes on disk, the view is made again.
function follow(view, file) {
  const key = view.toString();
  if (watching.has(key)) return;
  watching.set(key, file);
  fs.watchFile(file, { persistent: false, interval: 1500 }, (now, before) => { if (now.mtimeMs !== before.mtimeMs || now.size !== before.size) changed.fire(view); });
}

function unfollow(view) {
  const key = view.toString();
  const file = watching.get(key);
  if (file === undefined) return;
  watching.delete(key);
  fs.unwatchFile(file);
}

const tabsOf = () => vscode.window.tabGroups.all.flatMap((group) => group.tabs);
const textTab = (tab) => (tab.input instanceof vscode.TabInputText ? tab.input.uri : null);

// A JSON file that was just opened and is hard to read: its tab becomes the pretty view, in the same place.
async function prettify(tab) {
  const uri = textTab(tab);
  if (!enabled() || !uri || !isJsonFile(uri)) return;
  const key = uri.toString();
  if (raw.has(key) || busy.has(key)) return;
  busy.add(key);
  try {
    const text = await readJson(uri.fsPath);
    const here = () => tab.group.tabs.find((t) => textTab(t)?.toString() === key);    // (the tab may have been closed or edited meanwhile)
    if (text === null || !json.looksMinified(text) || !here() || here().isDirty) return;
    const view = await vscode.workspace.openTextDocument(viewUri(uri.fsPath));
    await vscode.window.showTextDocument(view, { viewColumn: tab.group.viewColumn, preview: tab.isPreview, preserveFocus: !tab.isActive });
    if (here() && !here().isDirty) await vscode.window.tabGroups.close(here());
  } catch {
    /* the file stays as it is */
  } finally {
    busy.delete(key);
  }
}

function activeTab() {
  return vscode.window.tabGroups.activeTabGroup.activeTab;
}

// The raw file, as text, in place of the pretty view.
async function openRaw(view) {
  const target = view instanceof vscode.Uri ? view : vscode.window.activeTextEditor?.document.uri;
  const file = target && target.scheme === SCHEME ? fileOf(target) : null;
  if (!file) return;
  const uri = vscode.Uri.file(file);
  raw.add(uri.toString());
  const tab = activeTab();
  await vscode.window.showTextDocument(uri, { viewColumn: tab?.group.viewColumn, preview: false });
  if (tab && tab.input instanceof vscode.TabInputText && tab.input.uri.scheme === SCHEME) await vscode.window.tabGroups.close(tab);
}

// A JSON file as text, in place of its pretty view (valid JSON only).
async function openPretty(file) {
  const target = file instanceof vscode.Uri ? file : vscode.window.activeTextEditor?.document.uri;
  if (!target || !isJsonFile(target)) return;
  const text = await readJson(target.fsPath);
  if (text === null || json.pretty(text) === null) return vscode.window.showWarningMessage(`${path.basename(target.fsPath)} is not valid JSON, or is too big: it can only be shown as it is.`);
  raw.delete(target.toString());
  const tab = activeTab();
  const view = await vscode.workspace.openTextDocument(viewUri(target.fsPath));
  await vscode.window.showTextDocument(view, { viewColumn: tab?.group.viewColumn, preview: false });
  if (tab && !tab.isDirty && textTab(tab)?.toString() === target.toString()) await vscode.window.tabGroups.close(tab);
}

// The "pretty" button is only offered on a JSON file that is hard to read.
function offerPretty() {
  const doc = vscode.window.activeTextEditor?.document;
  const offer = !!doc && isJsonFile(doc.uri) && doc.getText().length <= json.MAX_BYTES && json.looksMinified(doc.getText());
  return vscode.commands.executeCommand("setContext", "verdict.jsonMinified", offer);
}

// Markdown: the page and the code of the same file, one in place of the other.
function markdownCode() {
  return vscode.commands.executeCommand("workbench.action.reopenTextEditor");
}

async function markdownPage(uri) {
  const target = uri instanceof vscode.Uri ? uri : vscode.window.activeTextEditor?.document.uri;
  if (!target) return;
  const tab = activeTab();
  await vscode.commands.executeCommand("vscode.openWith", target, MARKDOWN_PREVIEW, vscode.window.tabGroups.activeTabGroup.viewColumn);
  if (tab && !tab.isDirty && textTab(tab)?.toString() === target.toString()) await vscode.window.tabGroups.close(tab);
}

// Is this file open in an editor already (as text or as the page)?
function isOpen(file) {
  return tabsOf().some((tab) => {
    const input = tab.input;
    return (input instanceof vscode.TabInputText || input instanceof vscode.TabInputCustom) && input.uri.fsPath === file;
  });
}

function activate(ctx) {
  const command = (id, fn) => ctx.subscriptions.push(vscode.commands.registerCommand(id, fn));
  command("verdict.markdownCode", markdownCode);
  command("verdict.markdownPreview", markdownPage);
  command("verdict.jsonRaw", openRaw);
  command("verdict.jsonPretty", openPretty);
  ctx.subscriptions.push(
    vscode.workspace.registerTextDocumentContentProvider(SCHEME, new PrettyJson()),
    vscode.window.tabGroups.onDidChangeTabs((e) => {
      e.opened.forEach(prettify);
      for (const tab of e.closed) {
        const uri = textTab(tab);
        if (uri) raw.delete(uri.toString());
      }
    }),
    vscode.workspace.onDidCloseTextDocument((doc) => { if (doc.uri.scheme === SCHEME) unfollow(doc.uri); }),
    vscode.window.onDidChangeActiveTextEditor(offerPretty),
    vscode.workspace.onDidSaveTextDocument(offerPretty),
    { dispose: () => { for (const file of watching.values()) fs.unwatchFile(file); watching.clear(); } },
    changed,
  );
  tabsOf().forEach(prettify);          // the tabs the editor restored when it opened
  offerPretty();
}

module.exports = { activate, isOpen, SCHEME, MARKDOWN_PREVIEW, viewUri, fileOf };
