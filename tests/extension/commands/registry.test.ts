import assert from "node:assert/strict";
import test from "node:test";
import type * as vscode from "vscode";
import { editor } from "../support/vscode-module";
import { ApiClient } from "../../../src/extension/api/client";
import { VerdictApi } from "../../../src/extension/api/verdict-api";
import { CommandRegistry } from "../../../src/extension/commands/registry";
import { SessionLoader } from "../../../src/extension/session/session-loader";
import { SessionState } from "../../../src/extension/session/session-state";
import { FakeApp } from "../support/fake-app";
import { aSession } from "../support/fixtures";

function registry(remembered = "s1") {
  editor.reset();
  const app = new FakeApp().on("GET sessions/s1", aSession());
  const state = new SessionState();
  const memory = { get: () => remembered, update: async () => {} } as unknown as vscode.Memento;
  const loader = new SessionLoader(new VerdictApi(new ApiClient("http://web:8000", app.fetch as typeof fetch)), state, memory);
  return { app, state, commands: new CommandRegistry(state, loader) };
}

test("a guarded command gets the session before it runs, and the arguments it was given", async () => {
  const r = registry();
  const seen: unknown[] = [];
  r.commands.guarded("verdict.x", (a: string, b: number) => { seen.push(r.state.current?.id, a, b); });
  await editor.run("verdict.x", "arg", 7);
  assert.deepEqual(seen, ["s1", "arg", 7]);
});

test("the session is only fetched when there is none yet", async () => {
  const r = registry();
  r.commands.guarded("verdict.x", () => {});
  await editor.run("verdict.x");
  await editor.run("verdict.x");
  assert.equal(r.app.calls("GET sessions/s1").length, 1);
});

test("a command that fails is shown to the person as a message and never thrown into the editor", async () => {
  const r = registry();
  r.commands.guarded("verdict.fails", () => { throw new Error("run the checks first"); });
  r.commands.guarded("verdict.fails.later", async () => { throw new Error("the app said no"); });
  await editor.run("verdict.fails");
  await editor.run("verdict.fails.later");
  assert.deepEqual(editor.messages.error, ["Verdict: run the checks first", "Verdict: the app said no"]);
});

test("a command is not run, and the reason is shown, when the session cannot be had", async () => {
  const r = registry();
  r.app.on("GET sessions/s1", { detail: "the app is starting" }, 503);
  let ran = false;
  r.commands.guarded("verdict.x", () => { ran = true; });
  await editor.run("verdict.x");
  assert.equal(ran, false);
  assert.deepEqual(editor.messages.error, ["Verdict: the app is starting"]);
});
