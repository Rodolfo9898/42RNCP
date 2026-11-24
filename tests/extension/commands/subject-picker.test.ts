import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { libraryChoices } from "../../../src/extension/commands/subject-picker";

const lib = {
  tracks: [{ id: "common-core", label: "Common Core" }, { id: "rncp", label: "RNCP" }, { id: "empty", label: "Empty" }],
  items: [{ path: "common-core/push_swap.pdf", name: "push_swap.pdf", track: "common-core" }, { path: "rncp/Mini-Shell.pdf", name: "Mini-Shell.pdf", track: "rncp" }],
};

test("a track with no PDF is not listed; the others are separators over their PDFs", () => {
  editor.reset();
  const choices = libraryChoices(lib, new Set(), "");
  assert.deepEqual(choices.map((c) => c.label), ["Common Core", "push_swap.pdf", "RNCP", "Mini-Shell.pdf"]);
  assert.deepEqual(choices.map((c) => c.path), [undefined, "common-core/push_swap.pdf", undefined, "rncp/Mini-Shell.pdf"]);
});

test("the project's subject is found whatever the case and punctuation of the names, and nothing is ticked without a project", () => {
  editor.reset();
  const picked = (project: string) => libraryChoices(lib, new Set(), project).filter((c) => c.picked).map((c) => c.label);
  assert.deepEqual(picked("minishell"), ["Mini-Shell.pdf"]);
  assert.deepEqual(picked("PUSH_SWAP"), ["push_swap.pdf"]);
  assert.deepEqual(picked("push-swap-bonus"), []);
  assert.deepEqual(picked(""), []);
});

test("a PDF already in the review is ticked and says so, over saying it is the project's", () => {
  editor.reset();
  const [, pushSwap] = libraryChoices(lib, new Set(["push_swap.pdf"]), "push_swap");
  assert.equal(pushSwap.description, "in this review");
  assert.equal(pushSwap.picked, true);
});
