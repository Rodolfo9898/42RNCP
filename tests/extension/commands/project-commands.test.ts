import assert from "node:assert/strict";
import * as path from "node:path";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { aSession } from "../support/fixtures";
import { running } from "../support/running";
import type { Running } from "../support/running";

const REPO = "PUT sessions/s1/repo";
const PROJECTS = { root: "projects", folders: ["rncp"], existing: [{ path: "rncp", git: false }, { path: "rncp/x", git: true }, { path: "other", git: true }] };
type Item = { label: string; description?: string };

function projects(run: Running, answer: object = PROJECTS): void {
  run.app.on("GET projects", answer).on(REPO, () => aSession({ repo: { path: "rncp/x", name: "x", commit: "9f8e7d6" } }));
}

test("a project already in the projects folder is picked from the list, with a clear mark on what is not a git repository", async () => {
  const run = await running();
  try {
    projects(run);
    editor.answers.quickPick = (items) => (items as Item[]).find((i) => i.label === "other");
    await editor.run("verdict.openProject");
    const [, items] = editor.calls.find((c) => c[0] === "quickPick") as [string, Item[]];
    assert.deepEqual(items.map((i) => [i.label, i.description]), [["rncp", "not a git repository"], ["rncp/x", ""], ["other", ""]]);
    assert.deepEqual(run.app.calls(REPO).map((r) => r.body), [{ kind: "existing", path: "other" }]);
  } finally { run.stop(); }
});

test("the project of the file that is open comes first, the deepest folder that holds it", async () => {
  const run = await running();
  try {
    projects(run);
    editor.openTab(path.join(run.projects, "rncp", "x", "main.c"));
    editor.answers.quickPick = (items) => (items as Item[])[0];
    await editor.run("verdict.openProject");
    const [, items] = editor.calls.find((c) => c[0] === "quickPick") as [string, Item[]];
    assert.deepEqual(items.map((i) => i.label), ["rncp/x", "rncp", "other"]);
    assert.equal(items[0].description, "the open file's project");
    assert.deepEqual(run.app.calls(REPO).map((r) => r.body), [{ kind: "existing", path: "rncp/x" }]);
  } finally { run.stop(); }
});

test("a chosen project is announced in the Output and shown in the Explorer", async () => {
  const run = await running();
  try {
    projects(run);
    editor.answers.quickPick = (items) => (items as Item[])[1];
    await editor.run("verdict.openProject");
    const log = editor.calls.filter((c) => c[0] === "output").map((c) => c[1] as string);
    assert.ok(log.some((l) => l.endsWith("Project: rncp/x @ 9f8e7d6")));
    const reveal = editor.calls.find((c) => c[0] === "command" && c[1] === "revealInExplorer") as unknown[];
    assert.equal((reveal[2] as { fsPath: string }).fsPath, path.join(run.projects, "rncp", "x"));
  } finally { run.stop(); }
});

test("nothing is chosen, nothing changes; and with no project at all the person is offered a clone", async () => {
  const run = await running();
  try {
    projects(run);
    await editor.run("verdict.openProject");
    assert.equal(run.app.calls(REPO).length, 0);
    projects(run, { root: "projects", folders: [], existing: [] });
    await editor.run("verdict.openProject");
    assert.ok(editor.messages.information.some((m) => m.startsWith("There is no project in ")));
    assert.ok(editor.messages.buttons.includes("Clone a Repository…"));
    editor.answers.pressed = "Clone a Repository…";
    await editor.run("verdict.openProject");
    assert.ok(editor.calls.some((c) => c[0] === "inputBox"), "the clone question was asked");
  } finally { run.stop(); }
});

test("a repository is cloned into a folder of the projects folder, under the name the person gives", async () => {
  const run = await running();
  try {
    projects(run);
    editor.answers.inputBox = (options) => (options.title === "Clone a repository" ? "git@vogsphere.42.fr:me/x.git" : "x");
    editor.answers.quickPick = (items) => (items as string[])[1];
    await editor.run("verdict.cloneProject");
    assert.deepEqual((editor.calls.find((c) => c[0] === "quickPick") as unknown[])[1], ["(the projects folder itself)", "rncp"]);
    assert.deepEqual(run.app.calls(REPO).map((r) => r.body), [{ kind: "clone", url: "git@vogsphere.42.fr:me/x.git", name: "x", destination: "rncp" }]);
    assert.deepEqual((editor.calls.find((c) => c[0] === "progress") as unknown[])[1], { location: 15, title: "Cloning git@vogsphere.42.fr:me/x.git…" });
  } finally { run.stop(); }
});

test("a clone into the projects folder itself, or when it has no sub-folder, sends no destination", async () => {
  const run = await running();
  try {
    projects(run);
    editor.answers.inputBox = (options) => (options.title === "Clone a repository" ? "https://github.com/me/x.git" : "");
    editor.answers.quickPick = (items) => (items as string[])[0];
    await editor.run("verdict.cloneProject");
    projects(run, { root: "projects", folders: [], existing: [] });
    await editor.run("verdict.cloneProject");
    assert.deepEqual(run.app.calls(REPO).map((r) => r.body), [
      { kind: "clone", url: "https://github.com/me/x.git", name: "", destination: "" },
      { kind: "clone", url: "https://github.com/me/x.git", name: "", destination: "" }]);
    assert.equal(editor.calls.filter((c) => c[0] === "quickPick").length, 1, "no destination question when there is no folder to choose");
  } finally { run.stop(); }
});

test("a clone is given up at any question the person leaves unanswered", async () => {
  const run = await running();
  try {
    projects(run);
    await editor.run("verdict.cloneProject");                                  // no URL
    editor.answers.inputBox = (options) => (options.title === "Clone a repository" ? "git@host:me/x.git" : undefined);
    await editor.run("verdict.cloneProject");                                  // no destination
    editor.answers.quickPick = (items) => (items as string[])[0];
    await editor.run("verdict.cloneProject");                                  // no name
    assert.equal(run.app.calls(REPO).length, 0);
  } finally { run.stop(); }
});
