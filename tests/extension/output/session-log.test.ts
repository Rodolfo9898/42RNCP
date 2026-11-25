import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { ChannelLog } from "../../../src/extension/output/channel-log";
import type { Logs } from "../../../src/extension/output/channel-log";
import { SessionLog } from "../../../src/extension/output/session-log";
import { SessionState } from "../../../src/extension/session/session-state";
import { aSession } from "../support/fixtures";

function tracking() {
  editor.reset();
  const channel = (name: string) => new ChannelLog(editor.api.window.createOutputChannel(name));
  const logs: Logs = { checks: channel("Verdict: Checks"), ai: channel("Verdict: AI review"), subjects: channel("Verdict: Subjects") };
  const state = new SessionState();
  const log = new SessionLog(state, logs);
  const change = (extra: Parameters<typeof aSession>[0]) => { state.set(aSession(extra)); log.track(); };
  const lines = (name: string) => editor.calls.filter((c) => c[0] === "output" && c[2] === name).map((c) => (c[1] as string).replace(/^\[\d\d:\d\d:\d\d\] /, ""));
  return { change, checks: () => lines("Verdict: Checks"), ai: () => lines("Verdict: AI review") };
}

test("the state of the checks is written when it changes, with the app's own message once", () => {
  const t = tracking();
  t.change({ state: "idle", message: "" });
  t.change({ state: "idle", message: "" });
  t.change({ state: "cloning", message: "Cloning x" });
  t.change({ state: "running", message: "Cloning x" });
  t.change({ state: "done", message: "12 checks" });
  t.change({ state: "error", message: "the sandbox is down" });
  assert.deepEqual(t.checks(), ["Ready.", "Cloning the repository…", "Cloning x", "Running the checks…", "The checks are done.", "12 checks",
    "The run failed: the sandbox is down", "the sandbox is down"]);
});

test("the AI review's steps are written once each, and its state when it changes after the first look", () => {
  const t = tracking();
  t.change({ ai: { state: "idle" } });
  t.change({ ai: { state: "running", progress: [{ text: "reading the code" }] } });
  t.change({ ai: { state: "running", progress: [{ text: "reading the code" }, { text: "asking the model" }] } });
  t.change({ ai: { state: "done", message: "4 items", progress: [{ text: "reading the code" }, { text: "asking the model" }, { text: "Done" }] } });
  assert.deepEqual(t.ai(), ["reading the code", "AI review: running", "asking the model", "Done", "AI review: done (4 items)"]);
});

test("a new AI run that starts its steps over is written from its first step", () => {
  const t = tracking();
  t.change({ ai: { state: "running", progress: [{ text: "one" }, { text: "two" }] } });
  t.change({ ai: { state: "running", progress: [{ text: "again" }] } });
  assert.deepEqual(t.ai().filter((l) => !l.startsWith("AI review")), ["one", "two", "again"]);
});
