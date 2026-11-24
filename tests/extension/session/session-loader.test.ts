import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import type * as vscode from "vscode";
import { ApiClient } from "../../../src/extension/api/client";
import { VerdictApi } from "../../../src/extension/api/verdict-api";
import { SessionLoader } from "../../../src/extension/session/session-loader";
import { SessionState } from "../../../src/extension/session/session-state";
import { FakeApp } from "../support/fake-app";
import { aSession } from "../support/fixtures";

function loading(remembered: string | undefined) {
  editor.reset();
  const app = new FakeApp();
  const state = new SessionState();
  const saved: Array<[string, string]> = [];
  const memory = { get: () => remembered, update: async (key: string, value: string) => { saved.push([key, value]); } } as unknown as vscode.Memento;
  const loader = new SessionLoader(new VerdictApi(new ApiClient("http://web:8000", app.fetch as typeof fetch)), state, memory);
  return { app, state, loader, saved };
}

test("the session the editor had is taken up again when the app still knows it", async () => {
  const load = loading("s1");
  load.app.on("GET sessions/s1", aSession());
  await load.loader.ensure();
  assert.equal(load.state.id, "s1");
  assert.deepEqual(load.app.requests.map((r) => r.method), ["GET"], "no new session");
  assert.deepEqual(load.saved, []);
});

test("a session the app does not know any more (404) is replaced by a new one, which is remembered", async () => {
  const load = loading("gone");
  load.app.on("GET sessions/gone", { detail: "session not found" }, 404).on("POST sessions", aSession({ id: "fresh" }), 201);
  await load.loader.ensure();
  assert.equal(load.state.id, "fresh");
  assert.deepEqual(load.saved, [["verdict.session", "fresh"]]);
});

test("the first time there is nothing remembered and a session is made", async () => {
  const load = loading(undefined);
  load.app.on("POST sessions", aSession({ id: "first" }), 201);
  await load.loader.ensure();
  assert.deepEqual(load.app.requests.map((r) => `${r.method} ${r.route}`), ["POST sessions"]);
  assert.deepEqual(load.saved, [["verdict.session", "first"]]);
});

test("an app that cannot be reached is an error, not a reason to forget the session", async () => {
  const load = loading("s1");
  load.app.on("GET sessions/s1", { detail: "boom" }, 503);
  await assert.rejects(load.loader.ensure(), { message: "boom", status: 503 });
  assert.deepEqual(load.saved, []);
  assert.equal(load.state.current, null);
});

test("a refresh reads the session again", async () => {
  const load = loading("s1");
  let state = "running";
  load.app.on("GET sessions/s1", () => aSession({ state }));
  await load.loader.ensure();
  state = "done";
  await load.loader.refresh();
  assert.equal(load.state.require().state, "done");
});
