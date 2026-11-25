import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import type { Recorded } from "../support/fake-app";
import { running } from "../support/running";

const ROUTE = "POST library/reorganizations";
const MOVES = [{ from: "samples/common-core/cpp00.pdf", to: "samples/common-core/cpp-modules/cpp00.pdf" },
  { from: "artifacts/common-core/cpp00", to: "artifacts/common-core/cpp-modules/cpp00" }];

test("with nothing to file it asks for a dry run and says so, and moves nothing", async () => {
  const run = await running();
  try {
    run.app.on(ROUTE, { dry_run: true, done: 0, moves: [] });
    await editor.run("verdict.subjectsReorganize");
    assert.deepEqual(run.app.calls(ROUTE).map((r) => r.body), [{ dry_run: true }]);
    assert.deepEqual(editor.messages.information, ["Every PDF and artifact is already in the folder of its series."]);
  } finally { run.stop(); }
});

test("what would move is written in the channel and asked about in a modal question; on Move it moves, and says how many", async () => {
  const run = await running();
  try {
    run.app.on(ROUTE, (request: Recorded) => ((request.body as { dry_run: boolean }).dry_run ? { dry_run: true, done: 0, moves: MOVES } : { dry_run: false, done: 2, moves: MOVES }));
    await editor.run("verdict.subjectsReorganize");
    assert.deepEqual(run.app.calls(ROUTE).map((r) => r.body), [{ dry_run: true }, { dry_run: false }]);
    assert.deepEqual(editor.output("Verdict: Subjects"), [
      "To move into the folders of their series:",
      "  samples/common-core/cpp00.pdf → samples/common-core/cpp-modules/cpp00.pdf",
      "  artifacts/common-core/cpp00 → artifacts/common-core/cpp-modules/cpp00",
      "Moved 2 PDFs and artifact folders into the folders of their series."]);
    assert.deepEqual(editor.messages.information, [
      "2 PDFs and artifact folders will move into the folders of their series (see the output)",
      "Moved 2 PDFs and artifact folders into the folders of their series."]);
    assert.deepEqual(editor.messages.buttons, ["Move"]);
    assert.deepEqual(editor.calls.filter((c) => c[0] === "show"), [["show", "Verdict: Subjects", true]]);
  } finally { run.stop(); }
});

test("when the person does not confirm, the dry run is all the app was asked", async () => {
  const run = await running();
  try {
    run.app.on(ROUTE, { dry_run: true, done: 0, moves: MOVES });
    editor.answers.confirm = false;
    await editor.run("verdict.subjectsReorganize");
    assert.deepEqual(run.app.calls(ROUTE).map((r) => r.body), [{ dry_run: true }]);
    assert.equal(editor.messages.information.length, 1, "the question, and no report of a move");
    assert.ok(editor.output("Verdict: Subjects").every((line) => !line.startsWith("Moved")));
  } finally { run.stop(); }
});

test("a refusal of the app is shown as an error", async () => {
  const run = await running();
  try {
    run.app.on(ROUTE, { detail: "the download service is not reachable" }, 503);
    await editor.run("verdict.subjectsReorganize");
    assert.deepEqual(editor.messages.error, ["Verdict: the download service is not reachable"]);
  } finally { run.stop(); }
});
