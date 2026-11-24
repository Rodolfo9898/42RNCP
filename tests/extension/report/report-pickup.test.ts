import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { aMerge } from "../support/fixtures";
import { running } from "../support/running";

// The extension running against a fake app: every pass of claude's report must reach the app's PUT claude-review, and the person must see it.
const COLLECT = "PUT sessions/s1/claude-review";

test("every time claude saves its report it is merged into verdict.md by itself, and the person is told", async () => {
  const run = await running();
  try {
    await run.ticks(3);
    assert.equal(run.app.calls(COLLECT).length, 0, "no report yet: nothing asked");
    fs.writeFileSync(run.report, "# first pass\n");
    await run.ticks(3);
    assert.equal(run.app.calls(COLLECT).length, 1, "the first pass was merged");
    assert.deepEqual(run.app.calls(COLLECT)[0].body, { force: false }, "the automatic pickup does not force anything");
    assert.deepEqual(editor.messages.information.slice(-1), ["Merged claude's answers (3 of 4 requirements) into verdict.md. 1 requirement(s) were not answered."]);
    const opened = editor.calls.filter((c) => c[0] === "command" && c[1] === "vscode.open");
    assert.equal(opened.length, 1, "verdict.md was opened");
    assert.equal((opened[0][2] as { path: string }).path, path.join(run.projects, "cub3d", "verdict.md"));
    assert.equal((opened[0][3] as { preserveFocus: boolean }).preserveFocus, true, "without taking the focus from the terminal claude works in");
    await run.ticks(4);
    assert.equal(run.app.calls(COLLECT).length, 1, "an unchanged report is not collected again");

    fs.writeFileSync(run.report, "# second pass, after the fixes\n");
    await run.ticks(3);
    assert.equal(run.app.calls(COLLECT).length, 2, "the second pass was merged too");
    assert.equal(editor.messages.information.filter((m) => m.startsWith("Merged")).length, 2);
    fs.writeFileSync(run.report, "# third pass, longer\n");
    await run.ticks(3);
    assert.equal(run.app.calls(COLLECT).length, 3);
  } finally { run.stop(); }
});

test("the view is read again after a merge, so the verdict shown is the merged one", async () => {
  const run = await running();
  try {
    const before = run.app.calls("GET sessions/s1").length;
    fs.writeFileSync(run.report, "# a pass\n");
    await run.ticks(3);
    assert.ok(run.app.calls("GET sessions/s1").length > before);
  } finally { run.stop(); }
});

test("a report the app says is for something else is explained, not merged; a down app is tried again", async () => {
  const run = await running();
  try {
    run.app.on(COLLECT, { detail: "could not reach the terminal service" }, 503);
    fs.writeFileSync(run.report, "# a pass\n");
    await run.ticks(5);
    assert.ok(run.app.calls(COLLECT).length >= 2, "tried again while the app was down");
    assert.deepEqual(editor.messages.information.filter((m) => m.startsWith("Merged")), []);
    run.app.on(COLLECT, aMerge({ new: false, written: false, stale: true }));
    await run.ticks(2);
    const log = editor.calls.filter((c) => c[0] === "output").map((c) => c[1]).join("\n");
    assert.match(log, /earlier run of the checks or another project/);
    const asked = run.app.calls(COLLECT).length;
    await run.ticks(4);
    assert.equal(run.app.calls(COLLECT).length, asked, "and then left alone until claude saves again");
  } finally { run.stop(); }
});

test("a report that changed nothing in the app is not announced", async () => {
  const run = await running();
  try {
    run.app.on(COLLECT, aMerge({ new: false, written: false }));
    fs.writeFileSync(run.report, "# a pass\n");
    await run.ticks(3);
    assert.equal(run.app.calls(COLLECT).length, 1);
    assert.deepEqual(editor.messages.information, []);
    assert.ok(!editor.calls.some((c) => c[1] === "vscode.open"));
  } finally { run.stop(); }
});
