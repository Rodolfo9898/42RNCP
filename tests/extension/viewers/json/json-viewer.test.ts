import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import test from "node:test";
import { editor } from "../../support/vscode-module";
import type { FakeDocument } from "../../support/fake-vscode";
import { until, pause, scratch } from "../../support/harness";
import { Configuration } from "../../../../src/extension/settings/configuration";
import { EditorTabs } from "../../../../src/extension/viewers/editor/editor-tabs";
import { fileOf } from "../../../../src/extension/viewers/json/json-files";
import { PrettyJsonProvider } from "../../../../src/extension/viewers/json/json-provider";
import { JsonViewer } from "../../../../src/extension/viewers/json/json-viewer";

function viewing() {
  editor.reset();
  const dir = scratch();
  const viewer = new JsonViewer(new Configuration(), new EditorTabs(), new PrettyJsonProvider());
  const disposables = viewer.register();
  const write = (name: string, text: string): string => { const file = path.join(dir, name); fs.writeFileSync(file, text); return file; };
  const prettyView = (): FakeDocument => [...editor.documents.values()].find((d) => d.uri.scheme === "verdict-json") as FakeDocument;
  return { viewer, dir, write, prettyView, tabs: () => editor.names(), stop: () => disposables.forEach((d) => d.dispose()) };
}

const MINIFIED = JSON.stringify({ levels: Array.from({ length: 30 }, (_, i) => ({ id: i, hosts: [`h${i}`, `g${i}`], on: true })) });

test("a JSON file saved on one line opens as a pretty read-only view; the file is not touched", async () => {
  const v = viewing();
  const file = v.write("level8.json", MINIFIED);
  editor.openTab(file);
  await until(() => v.tabs().join() === "verdict-json:level8 (pretty).json", "the pretty view replaces the tab");
  const view = v.prettyView();
  assert.ok(view.getText().split("\n").length > 100 && view.getText().startsWith('{\n  "levels": [\n    {\n      "id": 0,'));
  assert.equal(JSON.parse(view.getText()).levels.length, 30);
  assert.equal(fs.readFileSync(file, "utf8"), MINIFIED, "the raw file is as it was");
  assert.equal(fileOf(view.uri as never), file);
  v.stop();
});

test("JSON that is readable already, a dirty tab, a setting turned off, and other files are left alone", async () => {
  const v = viewing();
  editor.openTab(v.write("pretty.json", JSON.stringify(JSON.parse(MINIFIED), null, 2)));
  editor.openTab(v.write("short.json", '{"a":1}'));
  editor.openTab(v.write("compact.json", JSON.stringify({ a: Array.from({ length: 15 }, (_, i) => i) })));       // short enough to read as it is
  editor.openTab(v.write("dirty.json", MINIFIED), { isDirty: true });
  editor.openTab(v.write("notes.txt", MINIFIED));
  editor.openTab(v.write("broken.json", MINIFIED.slice(0, -3)));
  editor.settings["verdict.json.prettyOnOpen"] = false;
  editor.openTab(v.write("off.json", MINIFIED));
  await pause(150);
  assert.deepEqual(v.tabs(), ["file:pretty.json", "file:short.json", "file:compact.json", "file:dirty.json", "file:notes.txt", "file:broken.json", "file:off.json"]);
  v.stop();
});

test("the raw file can be opened from the pretty view, and stays raw until its tab is closed", async () => {
  const v = viewing();
  const file = v.write("level8.json", MINIFIED);
  editor.openTab(file);
  await until(() => v.tabs().join() === "verdict-json:level8 (pretty).json", "pretty");
  await editor.run("verdict.jsonRaw", v.prettyView().uri);
  await pause(100);
  assert.deepEqual(v.tabs(), ["file:level8.json"], "the raw file, in place of the view");
  await editor.closeTab(editor.group.tabs[0]);                        // closed: the next time it opens pretty again
  editor.openTab(file);
  await until(() => v.tabs().join() === "verdict-json:level8 (pretty).json", "pretty again");
  v.stop();
});

test("a JSON file shown raw goes back to its pretty view from the button, unless it is not valid JSON", async () => {
  const v = viewing();
  const file = v.write("level8.json", MINIFIED);
  editor.settings["verdict.json.prettyOnOpen"] = false;
  const tab = editor.openTab(file);
  await editor.run("verdict.jsonPretty", tab.input && (tab.input as { uri: unknown }).uri);
  assert.deepEqual(v.tabs(), ["verdict-json:level8 (pretty).json"], "the pretty view, in place of the text");
  const broken = editor.openTab(v.write("broken.json", "{oops"));
  await editor.run("verdict.jsonPretty", (broken.input as { uri: unknown }).uri);
  assert.match(editor.messages.warning.at(-1) as string, /broken\.json is not valid JSON, or is too big/);
  v.stop();
});

test("a pretty view follows its file and is made again when the file changes", async () => {
  const v = viewing();
  const file = v.write("level8.json", MINIFIED);
  editor.openTab(file);
  await until(() => v.tabs().join() === "verdict-json:level8 (pretty).json", "pretty");
  const uri = v.prettyView().uri;
  const provider = editor.providers["verdict-json"];
  let refreshed = 0;
  provider.onDidChange?.(() => refreshed++);
  fs.writeFileSync(file, JSON.stringify({ changed: "x".repeat(10), list: Array.from({ length: 80 }, (_, i) => i) }));
  await until(() => refreshed > 0, "the view is told to refresh", 800);
  assert.match(await provider.provideTextDocumentContent(uri as never, undefined as never) as string, /"changed": "xxxxxxxxxx"/);
  v.stop();
});

test("the button for the pretty view is only offered on a JSON file that is hard to read", async () => {
  const v = viewing();
  const offered = (): unknown => editor.calls.filter((c) => c[0] === "command" && c[2] === "verdict.jsonMinified").at(-1)?.[3];
  editor.settings["verdict.json.prettyOnOpen"] = false;
  editor.openTab(v.write("short.json", '{"a":1}'));
  await v.viewer.offerPretty();
  assert.equal(offered(), false);
  editor.openTab(v.write("long.json", MINIFIED));
  await v.viewer.offerPretty();
  assert.equal(offered(), true);
  editor.openTab(v.write("long.txt", MINIFIED));
  await v.viewer.offerPretty();
  assert.equal(offered(), false, "only JSON files");
  v.stop();
});
