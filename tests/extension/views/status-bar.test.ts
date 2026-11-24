import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import type * as vscode from "vscode";
import type { SessionView } from "../../../src/extension/api/types";
import { SessionState } from "../../../src/extension/session/session-state";
import { StatusBar } from "../../../src/extension/views/status-bar";
import { aSession } from "../support/fixtures";

function bar(extra: Partial<SessionView> | null) {
  editor.reset();
  const state = new SessionState();
  const item = editor.api.window.createStatusBarItem() as vscode.StatusBarItem;
  const status = new StatusBar(item, state);
  if (extra) state.set(aSession(extra));
  status.refresh();
  return { item, status };
}

test("the status bar names the project under review, its commit and the result, and a click picks another project", () => {
  const { item } = bar({});
  assert.equal(item.text, "$(shield) cub3d @ abc1234 · PASS");
  assert.equal(item.command, "verdict.openProject");
  assert.equal(item.tooltip, "Under review: cub3d. Click to review another project.");
  assert.equal(item.name, "Verdict: project");
  assert.equal(editor.statusItems[0].shown, true);
});

test("a project cloned from a URL says where from; before a run there is no result; while the app works the icon spins", () => {
  const { item } = bar({ repo: { path: "rncp/x", name: "x", url: "git@host:me/x.git" }, results: [], state: "running" });
  assert.equal(item.text, "$(sync~spin) x");
  assert.equal(item.tooltip, "Under review: rncp/x (git@host:me/x.git). Click to review another project.");
});

test("without a project it says so, and offers to pick one", () => {
  assert.equal(bar(null).item.text, "$(shield) no project");
  assert.equal(bar(null).item.tooltip, "Pick the project to review");
  assert.equal(bar({ repo: null }).item.text, "$(shield) no project");
});

test("when the app cannot be reached the status bar says so and why", () => {
  const { item, status } = bar(null);
  status.unavailable("the Verdict service (http://web:8000) cannot be reached: ECONNREFUSED");
  assert.equal(item.text, "$(warning) Verdict unavailable");
  assert.match(item.tooltip as string, /cannot be reached/);
});
