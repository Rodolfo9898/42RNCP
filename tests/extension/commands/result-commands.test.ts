import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { running } from "../support/running";

const PROGRESS = "PUT sessions/s1/progress";
const done = (answer: object) => ({ project: "cub3d", result: "PASS", symbol: "✅", before: "⬜", changed: true, ...answer });

test("Progress.md: the person confirms the result, it is recorded, and what changed is said", async () => {
  const run = await running();
  try {
    run.app.on(PROGRESS, done({}));
    await editor.run("verdict.updateProgress");
    assert.equal(run.app.calls(PROGRESS).length, 1);
    assert.ok(editor.messages.information.includes("cub3d: PASS. Record ✅ in Progress.md?"), "the question names the project, the result and the symbol");
    assert.ok(editor.messages.buttons.includes("Update Progress.md"));
    assert.equal(editor.messages.information.at(-1), "Progress.md: cub3d is now ✅ (was ⬜).");
    run.app.on(PROGRESS, done({ before: "✅", changed: false }));
    await editor.run("verdict.updateProgress");
    assert.equal(editor.messages.information.at(-1), "Progress.md already says ✅ for cub3d.");
    run.app.on(PROGRESS, done({ result: "FAIL", symbol: "❌", before: null }));
    await editor.run("verdict.updateProgress");
    assert.equal(editor.messages.information.at(-1), "Progress.md: cub3d is now ❌ (new row).");
    run.app.on(PROGRESS, done({ before: "" }));
    await editor.run("verdict.updateProgress");
    assert.equal(editor.messages.information.at(-1), "Progress.md: cub3d is now ✅ (was empty).");
  } finally { run.stop(); }
});

test("Progress.md is only touched when the person says so", async () => {
  const run = await running();
  try {
    editor.answers.confirm = false;
    await editor.run("verdict.updateProgress");
    assert.equal(run.app.calls(PROGRESS).length, 0);
  } finally { run.stop(); }
});

test("there is nothing to record before a run, or when the result is not one of the three", async () => {
  const before = await running({ results: [], summary: {} });
  try {
    await editor.run("verdict.updateProgress");
    assert.deepEqual(editor.messages.error, ["Verdict: run the checks first: there is no result to record yet"]);
  } finally { before.stop(); }
  const odd = await running({ summary: { overall: "UNKNOWN" } });
  try {
    await editor.run("verdict.updateProgress");
    assert.deepEqual(editor.messages.error, ["Verdict: there is no result to record yet (it says UNKNOWN)"]);
    assert.equal(odd.app.calls(PROGRESS).length, 0);
  } finally { odd.stop(); }
  const none = await running({ repo: null });
  try {
    await editor.run("verdict.updateProgress");
    assert.deepEqual(editor.messages.error, ["Verdict: open a project first"]);
  } finally { none.stop(); }
});

test("a result with issues is recorded with its own symbol", async () => {
  const run = await running({ summary: { overall: "PASS WITH ISSUES" } });
  try {
    run.app.on(PROGRESS, done({ result: "PASS WITH ISSUES", symbol: "⚠️" }));
    await editor.run("verdict.updateProgress");
    assert.ok(editor.messages.information.includes("cub3d: PASS WITH ISSUES. Record ⚠️ in Progress.md?"));
  } finally { run.stop(); }
});

test("the fix prompt opens as markdown and can be copied; when nothing is lacking there is none", async () => {
  const run = await running();
  try {
    run.app.on("GET sessions/s1/prompts/fix", { text: "# Fix these", must_fix: 2, look_at: 1, bonus: 0, issues: 3, chars: 11 });
    editor.answers.pressed = "Copy";
    await editor.run("verdict.fixPrompt");
    assert.equal([...editor.documents.values()].at(-1)?.languageId, "markdown");
    assert.equal([...editor.documents.values()].at(-1)?.getText(), "# Fix these");
    assert.equal(editor.messages.information.at(-1), "2 to fix, 1 to look at. Paste it into claude in the project's folder (you can edit it first).");
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.deepEqual(editor.calls.find((c) => c[0] === "clipboard"), ["clipboard", "# Fix these"]);
    editor.messages.information.length = 0;
    editor.documents.clear();
    run.app.on("GET sessions/s1/prompts/fix", { text: "", must_fix: 0, look_at: 0 });
    await editor.run("verdict.fixPrompt");
    assert.deepEqual(editor.messages.information, ["Nothing to fix: the review found nothing lacking."]);
    assert.equal(editor.documents.size, 0);
  } finally { run.stop(); }
});

test("verdict.md opens from the command of the title bar, with the focus", async () => {
  const run = await running();
  try {
    await editor.run("verdict.openVerdict");
    const opened = editor.calls.filter((c) => c[0] === "command" && c[1] === "vscode.open");
    assert.equal(opened.length, 1);
    assert.equal((opened[0][3] as { preserveFocus: boolean }).preserveFocus, false);
  } finally { run.stop(); }
});
