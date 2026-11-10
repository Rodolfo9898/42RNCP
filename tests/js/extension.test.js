"use strict";

// The Verdict extension, run in node with a fake `vscode` (fake_vscode.js): `node --test tests/js` (tests/test_extension.py does it).

const test = require("node:test");
const { mock } = test;
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const Module = require("module");
const fakeVscode = require("./fake_vscode");

const EXT = path.resolve(__dirname, "../../terminal/vscode/verdict");
let current = null;
const loadModule = Module._load;
Module._load = function (request, parent, isMain) {
  return request === "vscode" ? current : loadModule.call(this, request, parent, isMain);
};

// A fresh copy of the extension's modules (they keep state) talking to a fresh fake editor.
function fresh(name) {
  for (const key of Object.keys(require.cache)) if (key.startsWith(EXT)) delete require.cache[key];
  current = fakeVscode.create();
  return { vscode: current, mod: require(path.join(EXT, name)) };
}

const scratch = () => fs.mkdtempSync(path.join(os.tmpdir(), "verdict-ext-"));
const until = async (condition, what, tenths = 200) => {
  for (let i = 0; i < tenths; i++) {
    if (condition()) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.fail(`never happened: ${what}`);
};

// ---------------------------------------------------------------------------------------------- json.js

test("pretty-printing keeps every number, string and key exactly as the file has them", () => {
  const { mod } = fresh("json.js");
  const text = '{"b":[1,2,{"x":null,"e":[]}],"big":12345678901234567890,"a":1.50e+3,"s":"a,}\\"b","o":{},"b":true}';
  assert.equal(mod.pretty(text), [
    "{", '  "b": [', "    1,", "    2,", "    {", '      "x": null,', '      "e": []', "    }", "  ],",
    '  "big": 12345678901234567890,', '  "a": 1.50e+3,', '  "s": "a,}\\"b",', '  "o": {},', '  "b": true', "}", ""].join("\n"));
  assert.equal(mod.pretty("﻿[1]"), "[\n  1\n]\n");
  assert.equal(mod.pretty(" 42 "), "42\n");
});

test("what is not JSON is not pretty-printed", () => {
  const { mod } = fresh("json.js");
  for (const text of ["", "nope", '{"a":1,}', '{"a" 1}', "[1] [2]", '{"a":1}\n{"a":2}\n', "// comment\n{}", "[1,2"]) assert.equal(mod.pretty(text), null, text);
});

test("only a file that is hard to read, and gets easier, is shown pretty", () => {
  const { mod } = fresh("json.js");
  const wide = JSON.stringify({ levels: Array.from({ length: 40 }, (_, i) => ({ id: i, name: `level ${i}` })) });
  assert.ok(mod.looksMinified(wide), "one long line of data");
  assert.ok(!mod.looksMinified(JSON.stringify({ a: 1 })), "short");
  assert.ok(!mod.looksMinified(JSON.stringify(JSON.parse(wide), null, 2)), "already pretty");
  assert.ok(!mod.looksMinified(JSON.stringify({ text: "x".repeat(400) })), "one long string: printing it out does not help");
  assert.ok(!mod.looksMinified(`${wide.slice(0, -2)}, oops`), "not JSON");
  assert.equal(mod.viewOf(JSON.stringify({ a: 1 })), null);
  assert.ok(mod.viewOf(wide).split("\n").length > 100);
});

// ---------------------------------------------------------------------------------------------- report.js

test("a report is collected once it has stopped changing, once per version, and again when claude saves a new one", async () => {
  const { mod } = fresh("report.js");
  let file = null;
  const collected = [];
  const heard = [];
  const watch = mod.watcher({ look: async () => file, collect: async () => { collected.push(file); return { new: true }; }, done: (r) => heard.push(r) });
  await watch.tick();                                        // no report yet
  file = "v1";
  await watch.tick();                                        // seen for the first time: it may still be being written
  assert.deepEqual(collected, []);
  file = "v1b";
  await watch.tick();                                        // changed again
  assert.deepEqual(collected, []);
  await watch.tick();                                        // the same twice: collect
  assert.deepEqual(collected, ["v1b"]);
  await watch.tick(); await watch.tick();
  assert.deepEqual(collected, ["v1b"], "not again while it is the same");
  file = "v2";                                               // the next pass of claude's review
  await watch.tick(); await watch.tick();
  assert.deepEqual(collected, ["v1b", "v2"]);
  assert.equal(heard.length, 2);
});

test("a collect that fails is tried again on the next look, and two looks never overlap", async () => {
  const { mod } = fresh("report.js");
  let attempts = 0;
  let release;
  const heard = [];
  const watch = mod.watcher({
    look: async () => "v1",
    collect: () => { attempts++; if (attempts === 1) throw new Error("the app is down"); return new Promise((resolve) => { release = () => resolve({ new: true }); }); },
    done: (r) => heard.push(r),
  });
  await watch.tick();
  await watch.tick();                                        // collect throws
  assert.equal(attempts, 1);
  const slow = watch.tick();                                 // collect starts and waits
  await until(() => attempts === 2, "the second attempt");
  await watch.tick();                                        // overlapping: ignored
  assert.equal(attempts, 2);
  release();
  await slow;
  assert.equal(heard.length, 1);
  await watch.tick();
  assert.equal(attempts, 2, "done");
});

test("the signature of a report changes when the file is saved again, and is null without a file", async () => {
  const { mod } = fresh("report.js");
  const dir = scratch();
  const file = path.join(dir, mod.REPORT_NAME);
  assert.equal(await mod.signature(fs.promises.stat, file), null);
  fs.writeFileSync(file, "one");
  const one = await mod.signature(fs.promises.stat, file);
  fs.writeFileSync(file, "two, longer");
  assert.notEqual(await mod.signature(fs.promises.stat, file), one);
  assert.equal(await mod.signature(fs.promises.stat, dir), null, "a folder is no report");
});

// ---------------------------------------------------------------------------------------------- the merge, end to end

// The extension running against a fake app: every pass of claude's report must reach the app's `collect`, and the person must see it.
async function running() {
  const projects = scratch();
  const reports = scratch();
  fs.mkdirSync(path.join(projects, "cub3d"));
  fs.writeFileSync(path.join(projects, "cub3d", "verdict.md"), "# verdict\n");
  fs.mkdirSync(path.join(reports, "s1"));
  process.env.PROJECTS_DIR = projects;
  process.env.REPORTS_ROOT = reports;
  const { vscode, mod } = fresh("extension.js");
  const app = { collects: 0, answer: { new: true, written: true, stale: false, structured: true, assessed: 3, total: 4, verdict_file: "verdict.md" }, failing: false };
  const session = { id: "s1", state: "done", results: [{ title: "t", status: "pass" }], summary: { overall: "PASS" }, subjects: [], ai: { state: "idle" },
    repo: { path: "cub3d", name: "cub3d", commit: "abc1234" }, verdict_file: "verdict.md" };
  global.fetch = async (url, init = {}) => {
    const reply = (body, status = 200) => ({ ok: status < 300, status, statusText: "", text: async () => JSON.stringify(body) });
    if (url.endsWith("/claude-review/collect")) {
      app.collects++;
      return app.failing ? reply({ detail: "could not reach the terminal service" }, 503) : reply(app.answer);
    }
    if (url.endsWith("/api/sessions/s1")) return reply(session);
    if (url.endsWith("/api/health")) return reply({ llm: { provider: "claude-cli", configured: true } });
    if (url.endsWith("/api/sessions/s1/review-prompt")) return reply({ text: "review this project" });
    return reply({ detail: `unexpected ${init.method || "GET"} ${url}` }, 404);
  };
  mock.timers.enable({ apis: ["setInterval"] });
  const ctx = { subscriptions: [], globalState: { get: () => "s1", update: async () => {} } };
  mod.activate(ctx);
  await new Promise((resolve) => setTimeout(resolve, 30));          // (the session is fetched)
  const report = path.join(reports, "s1", "claude-review.md");
  const ticks = async (n) => { for (let i = 0; i < n; i++) { mock.timers.tick(2000); await new Promise((resolve) => setTimeout(resolve, 30)); } };
  return { vscode, app, report, ticks, ctx, stop: () => { ctx.subscriptions.forEach((s) => s.dispose && s.dispose()); mock.timers.reset(); }, projects };
}

test("every time claude saves its report it is merged into verdict.md by itself, and the person is told", async () => {
  const run = await running();
  try {
    await run.ticks(3);
    assert.equal(run.app.collects, 0, "no report yet: nothing asked");
    fs.writeFileSync(run.report, "# first pass\n");
    await run.ticks(3);
    assert.equal(run.app.collects, 1, "the first pass was merged");
    assert.deepEqual(run.vscode.messages.information.slice(-1), ["Merged claude's answers (3 of 4 requirements) into verdict.md. 1 requirement(s) were not answered."]);
    const opened = run.vscode.calls.filter((c) => c[0] === "command" && c[1] === "vscode.open");
    assert.equal(opened.length, 1, "verdict.md was opened");
    assert.equal(opened[0][2].path, path.join(run.projects, "cub3d", "verdict.md"));
    assert.equal(opened[0][3].preserveFocus, true, "without taking the focus from the terminal claude works in");
    await run.ticks(4);
    assert.equal(run.app.collects, 1, "an unchanged report is not collected again");

    fs.writeFileSync(run.report, "# second pass, after the fixes\n");
    await run.ticks(3);
    assert.equal(run.app.collects, 2, "the second pass was merged too");
    assert.equal(run.vscode.messages.information.filter((m) => m.startsWith("Merged")).length, 2);
    fs.writeFileSync(run.report, "# third pass, longer\n");
    await run.ticks(3);
    assert.equal(run.app.collects, 3);
  } finally { run.stop(); }
});

test("a report the app says is for something else is explained, not merged; a down app is tried again", async () => {
  const run = await running();
  try {
    run.app.failing = true;
    fs.writeFileSync(run.report, "# a pass\n");
    await run.ticks(5);
    assert.ok(run.app.collects >= 2, "tried again while the app was down");
    assert.deepEqual(run.vscode.messages.information.filter((m) => m.startsWith("Merged")), []);
    run.app.failing = false;
    run.app.answer = { new: false, written: false, stale: true };
    await run.ticks(2);
    const log = run.vscode.calls.filter((c) => c[0] === "output").map((c) => c[1]).join("\n");
    assert.match(log, /earlier run of the checks or another project/);
    const asked = run.app.collects;
    await run.ticks(4);
    assert.equal(run.app.collects, asked, "and then left alone until claude saves again");
  } finally { run.stop(); }
});

test("asking claude starts it with the prompt and does not wait for a click to merge its report", async () => {
  const run = await running();
  try {
    await run.vscode.commands.executeCommand("verdict.aiReview");
    const terminal = run.vscode.calls.find((c) => c[0] === "terminal")[1];
    assert.equal(terminal.shellPath, "python3");
    assert.deepEqual(terminal.shellArgs.slice(0, 3), ["-m", "verdict.editor", "claude"]);
    const promptFile = terminal.shellArgs[terminal.shellArgs.indexOf("--prompt-file") + 1];
    assert.equal(fs.readFileSync(promptFile, "utf8"), "review this project");
    fs.unlinkSync(promptFile);
    assert.ok(run.vscode.messages.information.includes("claude's report goes into verdict.md by itself, each time it saves it."));
    assert.ok(!run.vscode.messages.buttons.some((b) => /merge/i.test(b)), "no button to click to merge");
  } finally { run.stop(); }
});

// ---------------------------------------------------------------------------------------------- viewers.js

function viewing() {
  const dir = scratch();
  const { vscode, mod } = fresh("viewers.js");
  const ctx = { subscriptions: [] };
  mod.activate(ctx);
  const write = (name, text) => { const file = path.join(dir, name); fs.writeFileSync(file, text); return file; };
  return { vscode, mod, dir, write, ctx, tabs: () => vscode.names() };
}

const MINIFIED = JSON.stringify({ levels: Array.from({ length: 30 }, (_, i) => ({ id: i, hosts: [`h${i}`, `g${i}`], on: true })) });

test("a JSON file saved on one line opens as a pretty read-only view; the file is not touched", async () => {
  const v = viewing();
  const file = v.write("level8.json", MINIFIED);
  v.vscode.openTab(file);
  await until(() => v.tabs().join() === "verdict-json:level8 (pretty).json", "the pretty view replaces the tab");
  const view = [...v.vscode.documents.values()].find((d) => d.uri.scheme === "verdict-json");
  assert.ok(view.getText().split("\n").length > 100 && view.getText().startsWith('{\n  "levels": [\n    {\n      "id": 0,'));
  assert.equal(JSON.parse(view.getText()).levels.length, 30);
  assert.equal(fs.readFileSync(file, "utf8"), MINIFIED, "the raw file is as it was");
  assert.equal(v.mod.fileOf(view.uri), file);
});

test("JSON that is readable already, a dirty tab, a setting turned off, and other files are left alone", async () => {
  const v = viewing();
  v.vscode.openTab(v.write("pretty.json", JSON.stringify(JSON.parse(MINIFIED), null, 2)));
  v.vscode.openTab(v.write("short.json", '{"a":1}'));
  v.vscode.openTab(v.write("compact.json", JSON.stringify({ a: Array.from({ length: 15 }, (_, i) => i) })));       // short enough to read as it is
  v.vscode.openTab(v.write("dirty.json", MINIFIED), { isDirty: true });
  v.vscode.openTab(v.write("notes.txt", MINIFIED));
  v.vscode.openTab(v.write("broken.json", MINIFIED.slice(0, -3)));
  v.vscode.settings["verdict.json.prettyOnOpen"] = false;
  v.vscode.openTab(v.write("off.json", MINIFIED));
  await new Promise((resolve) => setTimeout(resolve, 150));
  assert.deepEqual(v.tabs(), ["file:pretty.json", "file:short.json", "file:compact.json", "file:dirty.json", "file:notes.txt", "file:broken.json", "file:off.json"]);
});

test("the raw file can be opened from the pretty view, and stays raw until its tab is closed", async () => {
  const v = viewing();
  const file = v.write("level8.json", MINIFIED);
  v.vscode.openTab(file);
  await until(() => v.tabs().join() === "verdict-json:level8 (pretty).json", "pretty");
  const view = [...v.vscode.documents.values()].find((d) => d.uri.scheme === "verdict-json");
  await v.vscode.handlers["verdict.jsonRaw"](view.uri);
  await new Promise((resolve) => setTimeout(resolve, 100));
  assert.deepEqual(v.tabs(), ["file:level8.json"], "the raw file, in place of the view");
  const tab = v.vscode.groups[0].tabs[0];
  await v.vscode.window.tabGroups.close(tab);                        // closed: the next time it opens pretty again
  v.vscode.openTab(file);
  await until(() => v.tabs().join() === "verdict-json:level8 (pretty).json", "pretty again");
});

test("a pretty view follows its file and is made again when the file changes", async () => {
  const v = viewing();
  const file = v.write("level8.json", MINIFIED);
  v.vscode.openTab(file);
  await until(() => v.tabs().join() === "verdict-json:level8 (pretty).json", "pretty");
  const uri = [...v.vscode.documents.values()].find((d) => d.uri.scheme === "verdict-json").uri;
  let refreshed = 0;
  v.vscode.providers["verdict-json"].onDidChange(() => refreshed++);
  fs.writeFileSync(file, JSON.stringify({ changed: "x".repeat(10), list: Array.from({ length: 80 }, (_, i) => i) }));
  await until(() => refreshed > 0, "the view is told to refresh", 800);
  assert.match(await v.vscode.providers["verdict-json"].provideTextDocumentContent(uri), /"changed": "xxxxxxxxxx"/);
  v.ctx.subscriptions.forEach((s) => s.dispose && s.dispose());
});

test("markdown: the page opens in place of the code, and the code in place of the page", async () => {
  const v = viewing();
  const file = v.write("README.md", "# hi\n");
  const tab = v.vscode.openTab(file);
  await v.vscode.handlers["verdict.markdownPreview"](v.vscode.groups[0].tabs[0].input.uri);
  const open = v.vscode.calls.find((c) => c[0] === "command" && c[1] === "vscode.openWith");
  assert.deepEqual([open[2].path, open[3]], [file, "vscode.markdown.preview.editor"]);
  assert.ok(!v.vscode.groups[0].tabs.includes(tab), "the code tab is closed");
  await v.vscode.handlers["verdict.markdownCode"]();
  assert.ok(v.vscode.calls.some((c) => c[0] === "command" && c[1] === "workbench.action.reopenTextEditor"));
  const dirty = v.vscode.openTab(v.write("EDITED.md", "x"), { isDirty: true });
  await v.vscode.handlers["verdict.markdownPreview"](dirty.input.uri);
  assert.ok(v.vscode.groups[0].tabs.includes(dirty), "a tab with unsaved changes stays open");
});
