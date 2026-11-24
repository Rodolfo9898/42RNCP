import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { running } from "../support/running";

const RUNS = "POST sessions/s1/runs";
const withSubject = { subjects: [{ name: "cub3d.pdf", kind: "subject", pages: 5, rules: [] }] };

test("a run saves the files, starts the checks on the app, shows their Output, and opens the new verdict.md when they end", async () => {
  const run = await running(withSubject);
  try {
    run.app.on(RUNS, () => ({ ...run.session, state: "running", results: [] }), 202);
    await editor.run("verdict.runChecks");
    assert.deepEqual(editor.calls.filter((c) => c[0] === "saveAll").map((c) => c.slice(1)), [[false]]);
    assert.equal(run.app.calls(RUNS).length, 1);
    const log = editor.calls.filter((c) => c[0] === "output").map((c) => c[1] as string);
    assert.ok(log.some((l) => l.endsWith("— a new run starts from nothing —")));
    assert.deepEqual(editor.calls.find((c) => c[0] === "show"), ["show", "Verdict: Checks", true]);
    assert.ok(!editor.calls.some((c) => c[1] === "vscode.open"), "not before the checks end");
    run.session.state = "done";
    await run.ticks(1);
    const opened = editor.calls.filter((c) => c[0] === "command" && c[1] === "vscode.open");
    assert.equal(opened.length, 1);
    assert.equal((opened[0][3] as { preserveFocus: boolean }).preserveFocus, true, "it does not take the focus from what the person is doing");
  } finally { run.stop(); }
});

test("without a project the person is asked for one first, and with none chosen there is no run", async () => {
  const run = await running({ repo: null, ...withSubject });
  try {
    run.app.on("GET projects", { root: "projects", folders: [], existing: [{ path: "x", git: true }] });
    await editor.run("verdict.runChecks");
    assert.equal(run.app.calls("GET projects").length, 1);
    assert.equal(run.app.calls(RUNS).length, 0);
  } finally { run.stop(); }
});

test("without a subject the person is asked for one first, and with none added there is no run", async () => {
  const run = await running({ subjects: [{ name: "en.norm.pdf", kind: "norm", rules: [] }] });
  try {
    run.app.on("GET library", { tracks: [{ id: "common-core", label: "Common Core" }], items: [{ path: "common-core/a.pdf", name: "a.pdf", track: "common-core" }] });
    await editor.run("verdict.runChecks");
    assert.equal(run.app.calls("GET library").length, 1, "the Norm alone is not a subject to review against");
    assert.equal(run.app.calls(RUNS).length, 0);
  } finally { run.stop(); }
});

test("Refresh reads the session again, and follows it when the app is still working", async () => {
  const run = await running({ state: "running" });
  try {
    const before = run.app.calls("GET sessions/s1").length;
    await editor.run("verdict.refresh");
    assert.equal(run.app.calls("GET sessions/s1").length, before + 1);
    run.session.state = "done";
    await run.ticks(1);
    const after = run.app.calls("GET sessions/s1").length;
    await run.ticks(2);
    assert.equal(run.app.calls("GET sessions/s1").length, after, "it follows the app until the work ends, and then stops");
  } finally { run.stop(); }
});

test("a session that was running when the editor opened is followed from the start", async () => {
  const run = await running({ state: "cloning" });
  try {
    const before = run.app.calls("GET sessions/s1").length;
    await run.ticks(1);
    assert.ok(run.app.calls("GET sessions/s1").length > before);
  } finally { run.stop(); }
});
