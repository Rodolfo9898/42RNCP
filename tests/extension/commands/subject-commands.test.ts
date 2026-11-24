import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { Uri } from "../support/fake-classes";
import { aSession } from "../support/fixtures";
import { running } from "../support/running";
import type { Running } from "../support/running";

const LIBRARY = {
  tracks: [{ id: "common-core", label: "Common Core" }, { id: "rncp", label: "RNCP" }],
  items: [{ path: "common-core/cub3d.pdf", name: "cub3d.pdf", track: "common-core" }, { path: "common-core/libft.pdf", name: "libft.pdf", track: "common-core" },
    { path: "rncp/minishell.pdf", name: "minishell.pdf", track: "rncp" }],
};
const ADD = "POST sessions/s1/subjects";
type Choice = { label: string; description?: string; picked?: boolean; path?: string; kind?: number };

function library(run: Running, lib: object = LIBRARY): void {
  run.app.on("GET library", lib).on(ADD, () => aSession({ subjects: [{ name: "x.pdf", kind: "subject", rules: [] }] }));
}

test("the library is shown by track, the project's own subject comes ticked, and what is in the review is marked", async () => {
  const run = await running({ subjects: [{ name: "libft.pdf", kind: "subject", rules: [] }] });
  try {
    library(run);
    await editor.run("verdict.addSubjects");
    const [, choices, options] = editor.calls.find((c) => c[0] === "quickPick") as [string, Choice[], { canPickMany: boolean; placeHolder: string }];
    assert.deepEqual(choices.map((c) => [c.label, c.description, c.picked]), [
      ["Common Core", undefined, undefined], ["cub3d.pdf", "this project's subject", true], ["libft.pdf", "in this review", true],
      ["RNCP", undefined, undefined], ["minishell.pdf", "", false]]);
    assert.equal(choices[0].kind, -1, "the track names are separators");
    assert.equal(options.canPickMany, true);
    assert.equal(options.placeHolder, "e.g. cub3d.pdf");
  } finally { run.stop(); }
});

test("the PDFs picked are added to the review by their place in the library; one that is in already is not asked for again", async () => {
  const run = await running({ subjects: [{ name: "libft.pdf", kind: "subject", rules: [] }] });
  try {
    library(run);
    editor.answers.quickPick = (items) => (items as Choice[]).filter((c) => c.picked || c.label === "minishell.pdf");
    await editor.run("verdict.addSubjects");
    assert.deepEqual(run.app.calls(ADD).map((r) => r.body), [{ paths: ["common-core/cub3d.pdf", "rncp/minishell.pdf"] }]);
    assert.equal(run.app.calls("POST library/common-core/subjects").length, 0, "nothing is uploaded: they are in the library");
  } finally { run.stop(); }
});

test("nothing picked, or only what the review has, adds nothing; an empty library says where PDFs go", async () => {
  const run = await running({ subjects: [{ name: "libft.pdf", kind: "subject", rules: [] }] });
  try {
    library(run);
    await editor.run("verdict.addSubjects");
    editor.answers.quickPick = (items) => (items as Choice[]).filter((c) => c.label === "libft.pdf");
    await editor.run("verdict.addSubjects");
    assert.equal(run.app.calls(ADD).length, 0);
    library(run, { tracks: LIBRARY.tracks, items: [] });
    await editor.run("verdict.addSubjects");
    assert.equal(editor.messages.information.at(-1), "The library is empty: put PDFs in samples/common-core/, samples/rncp/, or upload one.");
  } finally { run.stop(); }
});

test("an uploaded PDF goes into the library of the track the person names, and then into the review", async () => {
  const run = await running();
  try {
    library(run);
    const stored = { items: [{ path: "rncp/minishell.pdf", name: "minishell.pdf", track: "rncp", size: 4 }] };
    run.app.on("POST library/rncp/subjects", stored, 201);
    editor.files.set("/downloads/minishell.pdf", Buffer.from("%PDF"));
    editor.answers.openDialog = () => [Uri.file("/downloads/minishell.pdf")] as never;
    editor.answers.quickPick = (items) => (items as Array<{ id: string }>).find((i) => i.id === "rncp");
    await editor.run("verdict.uploadSubject");
    assert.deepEqual(run.app.requests.filter((r) => r.method !== "GET").map((r) => `${r.method} ${r.route}`), ["POST library/rncp/subjects", "POST sessions/s1/subjects"]);
    const form = run.app.calls("POST library/rncp/subjects")[0].form as FormData;
    assert.equal([...form.keys()].join(), "files", "the files only: the track is in the path");
    assert.equal(((form.get("files")) as File).name, "minishell.pdf");
    assert.equal(await ((form.get("files")) as File).text(), "%PDF");
    assert.deepEqual(run.app.calls(ADD)[0].body, { paths: ["rncp/minishell.pdf"] });
  } finally { run.stop(); }
});

test("the upload dialog starts in the project's folder, takes PDFs, and nothing happens when the person gives up", async () => {
  const run = await running();
  try {
    library(run);
    await editor.run("verdict.uploadSubject");
    const [, options] = editor.calls.find((c) => c[0] === "openDialog") as [string, { canSelectMany: boolean; filters: object; defaultUri: { fsPath: string } }];
    assert.equal(options.canSelectMany, true);
    assert.deepEqual(options.filters, { "Subject PDF": ["pdf"] });
    assert.ok(options.defaultUri.fsPath.endsWith("cub3d"));
    editor.answers.openDialog = () => [Uri.file("/downloads/a.pdf")] as never;
    editor.files.set("/downloads/a.pdf", Buffer.from("%PDF"));
    await editor.run("verdict.uploadSubject");                                           // no track chosen
    assert.equal(run.app.requests.filter((r) => r.method === "POST").length, 0);
  } finally { run.stop(); }
});

test("a subject is removed from the review by the name its row carries", async () => {
  const run = await running();
  try {
    run.app.on("DELETE sessions/s1/subjects/libft.pdf", () => aSession());
    await editor.run("verdict.removeSubject", { subject: "libft.pdf" });
    await editor.run("verdict.removeSubject", {});
    await editor.run("verdict.removeSubject");
    assert.equal(run.app.requests.filter((r) => r.method === "DELETE").length, 1);
  } finally { run.stop(); }
});
