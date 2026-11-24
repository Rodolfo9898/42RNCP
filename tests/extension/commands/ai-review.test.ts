import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { aCheck } from "../support/fixtures";
import { running } from "../support/running";

const AI = "POST sessions/s1/ai-review";
const llm = (extra: object) => ({ llm: { provider: "anthropic", configured: true, model: "claude-x", host: "api.example.com", ...extra } });

test("the AI is only asked about what the checks could not judge: after a run", async () => {
  const run = await running({ results: [] });
  try {
    await editor.run("verdict.aiReview");
    assert.deepEqual(editor.messages.warning, ["Run the checks first: the AI is asked about what they could not judge."]);
    assert.equal(run.app.calls("GET health").length, 0);
  } finally { run.stop(); }
});

test("when the app is set up for claude, the AI review is claude in a terminal", async () => {
  const run = await running();
  try {
    await editor.run("verdict.aiReview");
    assert.ok(editor.calls.some((c) => c[0] === "terminal"));
    assert.equal(run.app.calls(AI).length, 0);
  } finally { run.stop(); }
});

test("without any AI configured the person is told how to set one up", async () => {
  const run = await running({ results: [aCheck()] });
  try {
    run.app.on("GET health", llm({ configured: false }));
    await editor.run("verdict.aiReview");
    assert.match(editor.messages.warning[0], /No AI is configured: set ANTHROPIC_API_KEY/);
    assert.equal(run.app.calls(AI).length, 0);
  } finally { run.stop(); }
});

test("the source files only leave the computer after a question that names where they go; then the review is followed", async () => {
  const run = await running();
  try {
    run.app.on("GET health", llm({}));
    run.app.on(AI, () => ({ ...run.session, state: "done", ai: { state: "running", progress: [] } }), 202);
    await editor.run("verdict.aiReview");
    assert.deepEqual(editor.messages.warning, ["Send the source files of cub3d to api.example.com (claude-x)?"]);
    assert.equal(run.app.calls(AI).length, 1);
    run.session.ai = { state: "running" };
    await run.ticks(1);
    assert.ok(run.app.calls("GET sessions/s1").length > 1, "the session is read while the AI works");
  } finally { run.stop(); }
});

test("nothing is sent when the person declines the question", async () => {
  const run = await running();
  try {
    run.app.on("GET health", llm({}));
    editor.answers.confirm = false;
    await editor.run("verdict.aiReview");
    assert.equal(editor.messages.warning.length, 1);
    assert.equal(run.app.calls(AI).length, 0);
  } finally { run.stop(); }
});

test("the AI's log opens from its row of the Review view, and the review's own log is shown (without the focus) when it starts", async () => {
  const run = await running();
  try {
    await editor.run("verdict.showAiLog");
    assert.deepEqual(editor.calls.filter((c) => c[0] === "show"), [["show", "Verdict: AI review", undefined]]);
    run.app.on("GET health", llm({}));
    run.app.on(AI, () => run.session, 202);
    await editor.run("verdict.aiReview");
    assert.deepEqual(editor.calls.filter((c) => c[0] === "show").at(-1), ["show", "Verdict: AI review", true]);
  } finally { run.stop(); }
});
