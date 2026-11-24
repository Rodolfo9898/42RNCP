import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { running } from "../support/running";

const ENVIRONMENT = {
  ready: false,
  sandbox: { available: true, tools: [{ name: "cc", ok: true, detail: "cc 14" }, { name: "norminette", ok: false, required: true, detail: "not\ninstalled" },
    { name: "valgrind", ok: false, required: false, detail: "missing" }] },
  terminal: { available: false, error: "the terminal is not configured", tools: [] },
};

test("the environment check offers a quick and a full check, and shows the answer as a page", async () => {
  const run = await running();
  try {
    run.app.on("GET environment", ENVIRONMENT);
    editor.answers.quickPick = (items) => (items as Array<{ label: string }>).find((i) => i.label === "Quick");
    await editor.run("verdict.checkEnvironment");
    assert.equal(run.app.calls("GET environment").length, 1);
    assert.deepEqual((editor.calls.find((c) => c[0] === "progress") as unknown[])[1], { location: 15, title: "Checking the environment…" });
    const page = [...editor.documents.values()].at(-1);
    assert.equal(page?.languageId, "markdown");
    assert.equal(page?.getText(), [
      "# The environment: NOT ready", "", "## Sandbox (runs the checks, no network)", "",
      "- ✔ **cc**: cc 14", "- ✖ **norminette**: not installed", "- ⚠ **valgrind**: missing", "",
      "## Terminal (this editor, claude)", "", "✖ the terminal is not configured", "", "", "Only ✖ makes it not ready."].join("\n"));
  } finally { run.stop(); }
});

test("the full check is the same route with deep=true, and giving up asks nothing", async () => {
  const run = await running();
  try {
    run.app.on("GET environment?deep=true", { ...ENVIRONMENT, ready: true });
    await editor.run("verdict.checkEnvironment");
    assert.equal(run.app.requests.filter((r) => r.route.startsWith("environment")).length, 0);
    editor.answers.quickPick = (items) => (items as Array<{ label: string }>).find((i) => i.label === "Full");
    await editor.run("verdict.checkEnvironment");
    assert.equal(run.app.calls("GET environment?deep=true").length, 1);
    assert.match([...editor.documents.values()].at(-1)?.getText() as string, /^# The environment: ready/);
  } finally { run.stop(); }
});
