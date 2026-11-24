import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import test from "node:test";
import { editor } from "../../support/vscode-module";
import { scratch } from "../../support/harness";
import { EditorTabs } from "../../../../src/extension/viewers/editor/editor-tabs";
import { MarkdownViewer } from "../../../../src/extension/viewers/editor/markdown-viewer";

function viewing() {
  editor.reset();
  const dir = scratch();
  const disposables = new MarkdownViewer(new EditorTabs()).register();
  const write = (name: string, text: string): string => { const file = path.join(dir, name); fs.writeFileSync(file, text); return file; };
  return { write, stop: () => disposables.forEach((d) => d.dispose()) };
}

test("markdown: the page opens in place of the code, and the code in place of the page", async () => {
  const v = viewing();
  const file = v.write("README.md", "# hi\n");
  const tab = editor.openTab(file);
  await editor.run("verdict.markdownPreview", (editor.group.tabs[0].input as { uri: unknown }).uri);
  const open = editor.calls.find((c) => c[0] === "command" && c[1] === "vscode.openWith") as unknown[];
  assert.deepEqual([(open[2] as { path: string }).path, open[3]], [file, "vscode.markdown.preview.editor"]);
  assert.ok(!editor.group.tabs.includes(tab), "the code tab is closed");
  await editor.run("verdict.markdownCode");
  assert.ok(editor.calls.some((c) => c[0] === "command" && c[1] === "workbench.action.reopenTextEditor"));
  v.stop();
});

test("a tab with unsaved changes stays open when the page opens", async () => {
  const v = viewing();
  const dirty = editor.openTab(v.write("EDITED.md", "x"), { isDirty: true });
  await editor.run("verdict.markdownPreview", (dirty.input as { uri: unknown }).uri);
  assert.ok(editor.group.tabs.includes(dirty));
  v.stop();
});

test("without an address, the page is made of the file in the active editor; with nothing open there is nothing to do", async () => {
  const v = viewing();
  await editor.run("verdict.markdownPreview");
  assert.ok(!editor.calls.some((c) => c[1] === "vscode.openWith"));
  const file = v.write("NOTES.md", "# n\n");
  editor.openTab(file);
  await editor.run("verdict.markdownPreview");
  assert.equal(((editor.calls.find((c) => c[1] === "vscode.openWith") as unknown[])[2] as { path: string }).path, file);
  v.stop();
});
