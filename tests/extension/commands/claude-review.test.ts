import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { aMerge } from "../support/fixtures";
import { running } from "../support/running";

interface Terminal { name: string; cwd: string; shellPath: string; shellArgs: string[] }
const terminalOf = (): Terminal => editor.calls.find((c) => c[0] === "terminal")?.[1] as Terminal;

test("asking claude starts it with the prompt and does not wait for a click to merge its report", async () => {
  const run = await running();
  try {
    await editor.run("verdict.aiReview");
    const terminal = terminalOf();
    assert.equal(terminal.shellPath, "python3");
    assert.deepEqual(terminal.shellArgs.slice(0, 3), ["-m", "editor_launcher", "claude"]);
    const project = path.join(run.projects, "cub3d");
    assert.equal(terminal.cwd, project, "claude works in the project folder itself");
    assert.deepEqual(terminal.shellArgs.slice(3, 7), ["--session", "s1", "--project", project]);
    const promptFile = terminal.shellArgs[terminal.shellArgs.indexOf("--prompt-file") + 1];
    assert.equal(fs.readFileSync(promptFile, "utf8"), "review this project");
    assert.equal(fs.statSync(promptFile).mode & 0o777, 0o600, "the prompt is for this person only");
    fs.unlinkSync(promptFile);
    assert.equal(run.app.calls("GET sessions/s1/prompts/review").length, 1);
    assert.ok(editor.messages.information.includes("claude's report goes into verdict.md by itself, each time it saves it."));
    assert.ok(!editor.messages.buttons.some((b) => /merge/i.test(b)), "no button to click to merge");
    const log = editor.calls.filter((c) => c[0] === "output").map((c) => c[1]).join("\n");
    assert.match(log, /claude started in the terminal "claude: review" with the review prompt \(19 characters\)/);
  } finally { run.stop(); }
});

test("claude is not started when the person does not confirm", async () => {
  const run = await running();
  try {
    editor.answers.confirm = false;
    await editor.run("verdict.aiReview");
    assert.equal(terminalOf(), undefined);
    assert.equal(run.app.calls("GET sessions/s1/prompts/review").length, 0, "the prompt is not even asked for");
  } finally { run.stop(); }
});

test("merging by hand forces claude's saved report into verdict.md, tells what it did and opens the verdict", async () => {
  const run = await running();
  try {
    await editor.run("verdict.mergeClaudeReview");
    assert.deepEqual(run.app.calls("PUT sessions/s1/claude-review").map((r) => r.body), [{ force: true }]);
    assert.deepEqual(editor.messages.information.slice(-1), ["Merged claude's answers (3 of 4 requirements) into verdict.md. 1 requirement(s) were not answered."]);
    const opened = editor.calls.filter((c) => c[0] === "command" && c[1] === "vscode.open");
    assert.equal(opened.length, 1);
    assert.equal((opened[0][3] as { preserveFocus: boolean }).preserveFocus, false, "asked for by the person: it takes the focus");
    assert.ok(run.app.calls("GET sessions/s1").length >= 2, "the view was read again");
  } finally { run.stop(); }
});

test("when verdict.md could not be written the app's warning is shown, and a report without data is said to be text", async () => {
  const run = await running();
  try {
    run.app.on("PUT sessions/s1/claude-review", aMerge({ warning: "verdict.md could not be written into the repository", structured: false, problems: ["no data block"] }));
    await editor.run("verdict.mergeClaudeReview");
    assert.deepEqual(editor.messages.warning, ["verdict.md could not be written into the repository"]);
    assert.match(editor.messages.information.at(-1) as string, /^claude's report was added to verdict\.md as text/);
  } finally { run.stop(); }
});

test("when claude has saved nothing yet the person is told what the app says", async () => {
  const run = await running();
  try {
    run.app.on("PUT sessions/s1/claude-review", { detail: "claude has not saved its report yet." }, 404);
    await editor.run("verdict.mergeClaudeReview");
    assert.deepEqual(editor.messages.error, ["Verdict: claude has not saved its report yet."]);
  } finally { run.stop(); }
});
