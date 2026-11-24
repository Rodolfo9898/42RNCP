import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import type { Subject } from "../../../src/extension/api/types";
import { SessionState } from "../../../src/extension/session/session-state";
import { SubjectsTree } from "../../../src/extension/views/subjects-tree";
import { aSession } from "../support/fixtures";

const subjects: Subject[] = [
  { name: "push_swap.pdf", kind: "subject", track: "common-core", lang: "c", pages: 12, rules: [{ kind: "auto", title: "Makefile" }, { kind: "manual", title: "Explains" }] },
  { name: "en.norm.pdf", kind: "norm", pages: 3, rules: [] },
];

function tree(list: Subject[] = subjects) {
  editor.reset();
  const state = new SessionState();
  const view = new SubjectsTree(state);
  if (list) state.set(aSession({ subjects: list }));
  return { state, view };
}

test("the Subjects view lists the PDFs of the review, each opening itself on a click and carrying its name for the commands of its row", () => {
  const [subject, norm] = tree().view.getChildren();
  assert.equal(subject.label, "push_swap.pdf");
  assert.equal(subject.subject, "push_swap.pdf");
  assert.equal(subject.description, "common-core · 2 rules · C");
  assert.equal(subject.tooltip, "⚙ Makefile\n? Explains");
  assert.equal(subject.contextValue, "subject");
  assert.deepEqual(subject.command, { command: "verdict.openSubject", title: "Open the PDF", arguments: ["push_swap.pdf"] });
  assert.equal(norm.contextValue, "norm", "the Norm cannot be removed: no remove button on it");
  assert.equal(norm.description, "the Norm (C code was found)");
  assert.equal((norm.iconPath as { id: string }).id, "law");
});

test("it has no rows under a row, none before a session, and follows the session's changes", () => {
  const t = tree();
  const [subject] = t.view.getChildren();
  assert.deepEqual(t.view.getChildren(subject), []);
  assert.equal(t.view.getTreeItem(subject), subject);
  assert.deepEqual(new SubjectsTree(new SessionState()).getChildren(), []);
  let refreshed = 0;
  t.view.onDidChangeTreeData(() => refreshed++);
  t.state.set(aSession({ subjects: [] }));
  assert.equal(refreshed, 1);
  assert.deepEqual(t.view.getChildren(), []);
});
