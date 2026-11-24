import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import test from "node:test";
import { editor } from "../../support/vscode-module";
import { ApiClient } from "../../../../src/extension/api/client";
import { VerdictApi } from "../../../../src/extension/api/verdict-api";
import { ProjectFolder } from "../../../../src/extension/session/project-folder";
import { SessionState } from "../../../../src/extension/session/session-state";
import { DocumentViewer } from "../../../../src/extension/viewers/editor/document-viewer";
import { EditorTabs } from "../../../../src/extension/viewers/editor/editor-tabs";
import { VerdictViewer } from "../../../../src/extension/viewers/editor/verdict-viewer";
import { FakeApp } from "../../support/fake-app";
import { aSession } from "../../support/fixtures";
import { scratch } from "../../support/harness";

function viewing(extra = {}) {
  editor.reset();
  const projects = scratch();
  fs.mkdirSync(path.join(projects, "cub3d"));
  const verdict = path.join(projects, "cub3d", "verdict.md");
  const app = new FakeApp().on("GET sessions/s1/verdict.md", "# from the app");
  const state = new SessionState();
  state.set(aSession(extra));
  const api = new VerdictApi(new ApiClient("http://web:8000", app.fetch as typeof fetch));
  const tabs = new EditorTabs();
  const viewer = new VerdictViewer(api, state, new ProjectFolder(projects, state), tabs, new DocumentViewer());
  return { viewer, verdict, app, opened: () => editor.calls.filter((c) => c[0] === "command" && c[1] === "vscode.open") };
}

test("verdict.md of the project opens as a page, with the focus unless it opens by itself", async () => {
  const v = viewing();
  fs.writeFileSync(v.verdict, "# verdict\n");
  await v.viewer.open(false);
  await v.viewer.open(true);
  assert.equal(v.opened().length, 2);
  assert.deepEqual([(v.opened()[0][3] as { preserveFocus: boolean }).preserveFocus, (v.opened()[1][3] as { preserveFocus: boolean }).preserveFocus], [false, true]);
  assert.equal((v.opened()[0][2] as { path: string }).path, v.verdict);
});

test("an editor that has verdict.md already is left as it is when it opens by itself, and the person is not asked twice", async () => {
  const v = viewing();
  fs.writeFileSync(v.verdict, "# verdict\n");
  editor.openTab(v.verdict);
  await v.viewer.open(true);
  assert.equal(v.opened().length, 0, "VS Code reloads the open editor when the file changes");
  await v.viewer.open(false);
  assert.equal(v.opened().length, 1, "asked for by the person: it is brought up");
});

test("without a verdict.md in the project the app's own markdown is shown, and before a run there is nothing to show", async () => {
  const v = viewing();
  await v.viewer.open(false);
  assert.equal(v.app.calls("GET sessions/s1/verdict.md").length, 1);
  assert.equal([...editor.documents.values()].at(-1)?.getText(), "# from the app");
  assert.ok(editor.calls.some((c) => c[1] === "markdown.showPreview"));
  const before = viewing({ results: [] });
  await before.viewer.open(false);
  assert.deepEqual(editor.messages.information, ["Run the checks first."]);
  assert.equal(before.app.requests.length, 0);
});

test("after a run the new verdict.md is opened without taking the focus, and only when there is a result", async () => {
  const v = viewing();
  fs.writeFileSync(v.verdict, "# verdict\n");
  v.viewer.openAfterRun();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(v.opened().length, 1);
  assert.equal((v.opened()[0][3] as { preserveFocus: boolean }).preserveFocus, true);
  const empty = viewing({ results: [] });
  empty.viewer.openAfterRun();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.deepEqual(editor.messages.information, []);
});
