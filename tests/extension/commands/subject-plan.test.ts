import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { running } from "../support/running";
import type { LibraryPlan } from "../../../src/extension/api/types";

const SUBJECTS = "Verdict: Subjects";
const PLAN_ROUTE = "GET library/plan";
const missing = (...names: string[]) => names.map((name) => ({ name, path: `somewhere/${name}.pdf`, slug: name }));

function aPlan(extra: Partial<LibraryPlan> = {}): LibraryPlan {
  return {
    session: { valid: true, reason: "" },
    tracks: [
      { track: "common-core", label: "Common Core", total: 30, with_pdf: 28, missing: missing("libft", "get_next_line") },
      { track: "rncp", label: "RNCP", total: 4, with_pdf: 4, missing: [] },
      { track: "post-common-core", label: "Post Common Core", total: 10, with_pdf: 9, missing: missing("ft_yacc") },
    ],
    unknown: ["mystery"], misplaced: 85, ...extra,
  };
}

test("the plan is written as a report in the Subjects channel, and said in one line with a button that downloads", async () => {
  const run = await running();
  try {
    run.app.on(PLAN_ROUTE, aPlan());
    await editor.run("verdict.subjectsPlan");
    assert.equal(run.app.calls("GET library/plan?children=true").length, 1, "all the tracks, with the projects inside a piscine or a series");
    assert.deepEqual(editor.output(SUBJECTS), [
      "Subjects of the library against the intra", "The saved login to the intra can be used.",
      "", "Common Core: 30 subjects, 28 with a PDF, 2 missing", "  - libft", "  - get_next_line",
      "", "RNCP: 4 subjects, 4 with a PDF, 0 missing",
      "", "Post Common Core: 10 subjects, 9 with a PDF, 1 missing", "  - ft_yacc",
      "", "In no track: mystery",
      "", `85 not in the folder of their series: run "Verdict: File Subjects in Their Series Folders".`]);
    assert.deepEqual(editor.calls.filter((c) => c[0] === "show"), [["show", SUBJECTS, true]], "shown without taking the focus");
    assert.deepEqual(editor.messages.information, ["3 subjects missing in 2 tracks; 85 not filed in their series folder"]);
    assert.deepEqual(editor.messages.buttons, ["Download"]);
  } finally { run.stop(); }
});

test("the Download button runs the download command; without pressing it nothing starts", async () => {
  const run = await running();
  try {
    run.app.on(PLAN_ROUTE, aPlan());
    await editor.run("verdict.subjectsPlan");
    assert.equal(editor.calls.filter((c) => c[0] === "command" && c[1] === "verdict.subjectsDownload").length, 0);
    editor.answers.pressed = "Download";
    await editor.run("verdict.subjectsPlan");
    assert.equal(editor.calls.filter((c) => c[0] === "command" && c[1] === "verdict.subjectsDownload").length, 1);
    assert.equal(editor.calls.filter((c) => c[0] === "quickPick").length, 1, "the download asked which tracks");
  } finally { run.stop(); }
});

test("when nothing is missing it says so, without the button; the files out of place are still counted", async () => {
  const run = await running();
  try {
    const tracks = aPlan().tracks.map((track) => ({ ...track, missing: [], with_pdf: track.total }));
    run.app.on(PLAN_ROUTE, aPlan({ tracks, unknown: [], misplaced: 0 }));
    await editor.run("verdict.subjectsPlan");
    run.app.on(PLAN_ROUTE, aPlan({ tracks, unknown: [], misplaced: 85 }));
    await editor.run("verdict.subjectsPlan");
    assert.deepEqual(editor.messages.information, ["Nothing missing", "Nothing missing; 85 not filed in their series folder"]);
    assert.deepEqual(editor.messages.buttons, []);
    assert.ok(!editor.output(SUBJECTS).some((l) => l.startsWith("In no track")), "no unknown names, no line about them");
  } finally { run.stop(); }
});

test("a login that cannot be used is in the report with its reason and what to run on the computer, and the line has no download button", async () => {
  const run = await running();
  try {
    const tracks = [{ track: "rncp", label: "RNCP", total: 4, with_pdf: 3, missing: missing("minishell") }];
    run.app.on(PLAN_ROUTE, aPlan({ tracks, unknown: [], misplaced: 0, session: { valid: false, reason: "the session expired" } }));
    await editor.run("verdict.subjectsPlan");
    assert.deepEqual(editor.output(SUBJECTS).slice(0, 3), [
      "Subjects of the library against the intra", "The saved login to the intra cannot be used: the session expired",
      "To download: run `make samples-login` on your computer."]);
    assert.deepEqual(editor.messages.warning, ["1 subject missing in 1 track; the saved login to the intra cannot be used: run `make samples-login` on your computer"]);
    assert.deepEqual(editor.messages.information, []);
    assert.deepEqual(editor.messages.buttons, []);
  } finally { run.stop(); }
});

test("a plan the app cannot make is shown as an error, and nothing is written", async () => {
  const run = await running();
  try {
    run.app.on(PLAN_ROUTE, { detail: "the download service is not reachable" }, 503);
    await editor.run("verdict.subjectsPlan");
    assert.deepEqual(editor.messages.error, ["Verdict: the download service is not reachable"]);
    assert.deepEqual(editor.output(SUBJECTS), []);
  } finally { run.stop(); }
});
