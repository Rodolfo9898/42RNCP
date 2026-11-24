import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { SessionState } from "../../../src/extension/session/session-state";
import { aSession } from "../support/fixtures";

test("there is no session until one is set, and asking for it then says so", () => {
  editor.reset();
  const state = new SessionState();
  assert.equal(state.current, null);
  assert.equal(state.busy(), false);
  assert.throws(() => state.require(), /not loaded yet/);
  assert.throws(() => state.id, /not loaded yet/);
});

test("everything that shows the session is told when it changes", () => {
  editor.reset();
  const state = new SessionState();
  let told = 0;
  state.onDidChange(() => told++);
  const view = state.set(aSession());
  assert.equal(state.current, view);
  assert.equal(state.id, "s1");
  assert.equal(told, 1);
});

test("the app is busy while it clones, runs the checks, or runs the AI review", () => {
  editor.reset();
  const state = new SessionState();
  const busy = (extra: Parameters<typeof aSession>[0]): boolean => { state.set(aSession(extra)); return state.busy(); };
  assert.equal(busy({ state: "done" }), false);
  assert.equal(busy({ state: "idle" }), false);
  assert.equal(busy({ state: "error" }), false);
  assert.equal(busy({ state: "running" }), true);
  assert.equal(busy({ state: "cloning" }), true);
  assert.equal(busy({ state: "done", ai: { state: "running" } }), true);
  assert.equal(busy({ state: "done", ai: { state: "done" } }), false);
});
