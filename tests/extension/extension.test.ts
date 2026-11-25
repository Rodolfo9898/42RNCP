import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import test from "node:test";
import { editor } from "./support/vscode-module";
import { EXTENSION_DIR } from "./support/harness";
import { running } from "./support/running";

// activate(): the composition root. What the manifest declares must be what it wires.
const MANIFEST = JSON.parse(fs.readFileSync(path.join(EXTENSION_DIR, "package.json"), "utf8"));

test("activating registers every command the manifest declares, and nothing it does not declare", async () => {
  const run = await running();
  try {
    const declared = MANIFEST.contributes.commands.map((c: { command: string }) => c.command).sort();
    const internal = ["verdict.showText", "verdict.showAiLog"];             // (called by the rows of the Review view, not offered in a menu)
    assert.deepEqual(Object.keys(editor.handlers).sort(), [...declared, ...internal].sort());
  } finally { run.stop(); }
});

test("every menu entry uses a command the manifest declares, on a view or a place that exists", () => {
  const declared = new Set(MANIFEST.contributes.commands.map((c: { command: string }) => c.command));
  const views = new Set(MANIFEST.contributes.views.verdict.map((v: { id: string }) => `view == ${v.id}`));
  for (const [place, entries] of Object.entries(MANIFEST.contributes.menus) as Array<[string, Array<{ command: string; when: string }>]>) {
    for (const entry of entries) {
      assert.ok(declared.has(entry.command), `${place}: ${entry.command} is not declared`);
      if (place === "view/title") assert.ok(views.has(entry.when), `${entry.command}: ${entry.when} is not a view of the extension`);
    }
  }
  assert.ok(MANIFEST.contributes.commands.every((c: { title: string; category: string }) => c.title && c.category === "Verdict"));
});

test("the subjects commands are in the title bar of the Subjects view (download as a button, the others under the menu) and in the Command Palette", () => {
  const where = Object.fromEntries(MANIFEST.contributes.menus["view/title"].filter((m: { when: string }) => m.when === "view == verdict.subjects")
    .map((m: { command: string; group: string }) => [m.command, m.group]));
  assert.deepEqual(where, { "verdict.addSubjects": "navigation@1", "verdict.uploadSubject": "navigation@2", "verdict.subjectsDownload": "navigation@3",
    "verdict.subjectsPlan": "more@1", "verdict.subjectsReorganize": "more@2" });
  const titles = Object.fromEntries(MANIFEST.contributes.commands.map((c: { command: string; title: string; icon?: string }) => [c.command, [c.title, c.icon]]));
  assert.deepEqual(titles["verdict.subjectsPlan"][0], "Show What Subjects Are Missing");
  assert.deepEqual(titles["verdict.subjectsDownload"], ["Download Subjects from the Intra\u2026", "$(cloud-download)"]);
  assert.deepEqual(titles["verdict.subjectsReorganize"][0], "File Subjects in Their Series Folders");
  const hidden = MANIFEST.contributes.menus.commandPalette.filter((m: { when: string }) => m.when === "false").map((m: { command: string }) => m.command);
  for (const id of ["verdict.subjectsPlan", "verdict.subjectsDownload", "verdict.subjectsReorganize"]) assert.ok(!hidden.includes(id), `${id} can be run from the palette`);
});

test("the two views of the manifest are filled by the extension, and the status bar names the project", async () => {
  const run = await running();
  try {
    const views = MANIFEST.contributes.views.verdict.map((v: { id: string }) => v.id).sort();
    assert.deepEqual(Object.keys(editor.trees).sort(), views);
    assert.equal(editor.statusItems.length, 1);
    assert.equal(editor.statusItems[0].text, "$(shield) cub3d @ abc1234 · PASS");
    const rows = editor.trees["verdict.review"].getChildren() as Array<{ item: { label: string } }>;
    assert.equal(rows[0].item.label, "Result: PASS");
  } finally { run.stop(); }
});

test("everything the extension created is released when the editor disposes its subscriptions", async () => {
  const run = await running({ state: "running" });                   // (the session is followed: a timer is asking the app every second)
  try {
    run.ctx.subscriptions.forEach((s) => s.dispose());
    const before = run.app.requests.length;
    await run.ticks(3);
    assert.equal(run.app.requests.length, before, "no timer is left asking the app");
  } finally { run.stop(); }
});

test("when the app cannot be reached the status bar and the Output say so, and the commands say it too", async () => {
  const run = await running({}, false);
  try {
    assert.equal(editor.statusItems[0].text, "$(warning) Verdict unavailable");
    assert.match(editor.statusItems[0].tooltip as string, /the Verdict service \(http:\/\/.+\) cannot be reached: connect ECONNREFUSED/);
    const log = editor.calls.filter((c) => c[0] === "output" && c[2] === "Verdict: Checks").map((c) => c[1] as string);
    assert.ok(log.some((l) => l.includes("cannot be reached")));
    await editor.run("verdict.runChecks");
    assert.match(editor.messages.error[0], /^Verdict: the Verdict service .* cannot be reached/);
  } finally { run.stop(); }
});

test("a session that was running when the editor opened is followed, and the result is read once it ends", async () => {
  const run = await running({ state: "running", results: [] });
  try {
    run.session.state = "done";
    run.session.results = [{ title: "t", status: "pass" }];
    await run.ticks(1);
    const rows = editor.trees["verdict.review"].getChildren() as Array<{ item: { label: string } }>;
    assert.equal(rows[0].item.label, "Result: PASS");
  } finally { run.stop(); }
});
