import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../../support/vscode-module";
import { DocumentViewer } from "../../../../src/extension/viewers/editor/document-viewer";

test("a log or a prompt that is not a file opens as a document of its own language, beside the current tab when asked", async () => {
  editor.reset();
  const viewer = new DocumentViewer();
  await viewer.showText("line 1\nline 2", "log");
  await viewer.showText("# fix", "markdown", true);
  const shown = editor.calls.filter((c) => c[0] === "showTextDocument");
  assert.equal(shown.length, 2);
  assert.deepEqual([...editor.documents.values()].map((d) => [d.languageId, d.getText()]), [["log", "line 1\nline 2"], ["markdown", "# fix"]]);
  assert.deepEqual(shown.map((c) => (c[2] as { viewColumn?: number }).viewColumn), [undefined, -2]);
});

test("markdown that is not a file is shown as the page", async () => {
  editor.reset();
  await new DocumentViewer().showMarkdown("# the environment");
  assert.equal([...editor.documents.values()][0].languageId, "markdown");
  assert.deepEqual(editor.calls.filter((c) => c[0] === "command").map((c) => c[1]), ["markdown.showPreview"]);
});

test("the log of a check, in the Review view, opens through the command verdict.showText", async () => {
  editor.reset();
  const viewer = new DocumentViewer();
  viewer.register();
  await editor.run("verdict.showText", "make: *** error", "log");
  assert.equal([...editor.documents.values()][0].getText(), "make: *** error");
});
