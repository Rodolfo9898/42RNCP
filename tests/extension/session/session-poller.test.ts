import assert from "node:assert/strict";
import test, { mock } from "node:test";
import { editor } from "../support/vscode-module";
import { ApiClient } from "../../../src/extension/api/client";
import { VerdictApi } from "../../../src/extension/api/verdict-api";
import { SessionLoader } from "../../../src/extension/session/session-loader";
import { SessionPoller } from "../../../src/extension/session/session-poller";
import { SessionState } from "../../../src/extension/session/session-state";
import type * as vscode from "vscode";
import { FakeApp } from "../support/fake-app";
import { aSession } from "../support/fixtures";
import { pause } from "../support/harness";

function polling() {
  editor.reset();
  const app = new FakeApp();
  const view = { state: "running" };
  app.on("GET sessions/s1", () => aSession({ state: view.state }));
  const state = new SessionState();
  const memory = { get: () => "s1", update: async () => {} } as unknown as vscode.Memento;
  const loader = new SessionLoader(new VerdictApi(new ApiClient("http://web:8000", app.fetch as typeof fetch)), state, memory);
  mock.timers.enable({ apis: ["setInterval"] });
  const poller = new SessionPoller(loader, state);
  const second = async (n = 1) => { for (let i = 0; i < n; i++) { mock.timers.tick(1000); await pause(20); } };
  return { app, view, state, loader, poller, second, stop: () => { poller.dispose(); mock.timers.reset(); } };
}

test("the session is read every second while the app works, and the callbacks run once when it stops", async () => {
  const p = polling();
  try {
    await p.loader.ensure();
    const done: string[] = [];
    p.poller.start(() => done.push("opened verdict"));
    await p.second(3);
    assert.equal(p.app.calls("GET sessions/s1").length, 4, "one at the start, one per second");
    assert.deepEqual(done, []);
    p.view.state = "done";
    await p.second(1);
    assert.deepEqual(done, ["opened verdict"]);
    await p.second(3);
    assert.equal(p.app.calls("GET sessions/s1").length, 5, "it stopped asking");
    assert.deepEqual(done, ["opened verdict"], "and does not call back again");
  } finally { p.stop(); }
});

test("a start while it already polls adds its callback without a second timer", async () => {
  const p = polling();
  try {
    await p.loader.ensure();
    const done: string[] = [];
    p.poller.start(() => done.push("first"));
    p.poller.start(() => done.push("second"));
    p.poller.start();
    p.view.state = "done";
    await p.second(1);
    assert.equal(p.app.calls("GET sessions/s1").length, 2, "one read per second, not three");
    assert.deepEqual(done, ["first", "second"]);
  } finally { p.stop(); }
});

test("a read that fails is tried again on the next second", async () => {
  const p = polling();
  try {
    await p.loader.ensure();
    const done: string[] = [];
    p.poller.start(() => done.push("done"));
    p.app.on("GET sessions/s1", { detail: "down" }, 503);
    await p.second(2);
    assert.deepEqual(done, [], "an unreadable session does not end the wait");
    p.app.on("GET sessions/s1", () => aSession({ state: "done" }));
    await p.second(1);
    assert.deepEqual(done, ["done"]);
  } finally { p.stop(); }
});

test("disposing the poller stops its timer, so a callback that was waiting for the end never runs", async () => {
  const p = polling();
  try {
    await p.loader.ensure();
    p.view.state = "done";
    const done: string[] = [];
    p.poller.start(() => done.push("x"));
    p.poller.dispose();
    await p.second(2);
    assert.deepEqual(done, [], "disposed before its first tick");
    assert.equal(p.app.calls("GET sessions/s1").length, 1);
  } finally { p.stop(); }
});

test("when the work has ended the poller can follow the next piece of work", async () => {
  const p = polling();
  try {
    await p.loader.ensure();
    p.view.state = "done";
    p.poller.start();
    await p.second(1);
    const reads = p.app.calls("GET sessions/s1").length;
    const done: string[] = [];
    p.poller.start(() => done.push("the second run ended"));
    await p.second(1);
    assert.equal(p.app.calls("GET sessions/s1").length, reads + 1, "asking again");
    assert.deepEqual(done, ["the second run ended"]);
  } finally { p.stop(); }
});
