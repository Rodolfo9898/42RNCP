import assert from "node:assert/strict";
import * as path from "node:path";
import test from "node:test";
import { editor } from "../support/vscode-module";
import type { CheckResult, SessionView } from "../../../src/extension/api/types";
import { ProjectFolder } from "../../../src/extension/session/project-folder";
import { SessionState } from "../../../src/extension/session/session-state";
import { CheckNodeBuilder } from "../../../src/extension/views/check-nodes";
import type { ReviewNode } from "../../../src/extension/views/review-node";
import { ReviewTree } from "../../../src/extension/views/review-tree";
import { aCheck, aSession } from "../support/fixtures";

function tree(extra: Partial<SessionView> = {}, busy = false) {
  editor.reset();
  const state = new SessionState();
  state.set(aSession({ state: busy ? "running" : "done", ...extra }));
  const review = new ReviewTree(state, new CheckNodeBuilder(new ProjectFolder("/projects", state)));
  const labels = (nodes: ReviewNode[]) => nodes.map((n) => String(n.item.label));
  return { state, review, top: () => review.getChildren(), labels, childrenOf: (node: ReviewNode) => review.getChildren(node) };
}

const mixed: CheckResult[] = [aCheck({ title: "Norm", status: "fail" }), aCheck({ title: "Makefile", status: "pass" }), aCheck({ title: "Leaks", status: "warn" }),
  aCheck({ title: "Readme", status: "manual", rule_id: "r1" }), aCheck({ title: "Other", status: "pass" })];

test("the Review view is empty until there is a project", () => {
  assert.deepEqual(tree({ repo: null }).top(), []);
});

test("it starts with the result, then the checks grouped worst first; what passed or does not apply is folded", () => {
  const t = tree({ results: mixed, summary: { overall: "FAIL", decided_by: "checks" } });
  const top = t.top();
  assert.deepEqual(t.labels(top), ["Result: FAIL", "Failed (1)", "Warnings (1)", "Needs manual review (1)", "Passed (2)"]);
  assert.equal(top[0].item.description, "from the checks");
  assert.deepEqual(top.slice(1).map((n) => n.item.collapsibleState), [2, 2, 2, 1]);
  assert.deepEqual(t.labels(t.childrenOf(top[4])), ["Makefile", "Other"]);
});

test("before a run it says so and offers the run; while the app works it says running", () => {
  const before = tree({ results: [], summary: {} });
  const [result] = before.top();
  assert.equal(result.item.label, "Not run yet");
  assert.equal(result.item.description, "Run the checks");
  assert.equal(result.item.command?.command, "verdict.runChecks");
  const during = tree({ results: [], summary: {}, state: "running" }, true).top()[0];
  assert.equal(during.item.label, "Running…");
  assert.equal(during.item.command, undefined, "a run is under way: no button");
  assert.equal((during.item.iconPath as { id: string }).id, "sync~spin");
});

test("a result decided by claude says so", () => {
  const [result] = tree({ results: mixed, summary: { overall: "PASS WITH ISSUES", decided_by: "claude", reason: "claude looked at 3 items" } }).top();
  assert.equal(result.item.description, "decided by claude");
  assert.equal(result.item.tooltip, "claude looked at 3 items");
});

test("the AI review shows when there is one, and opens its log", () => {
  assert.equal(tree({ results: mixed }).top().some((n) => String(n.item.label).startsWith("AI review")), false, "idle: nothing");
  const node = tree({ results: mixed, ai: { state: "running", message: "2 of 5" } }).top()[1];
  assert.equal(node.item.label, "AI review: running");
  assert.equal(node.item.description, "2 of 5");
  assert.equal(node.item.command?.command, "verdict.showAiLog");
});

test("a check the scripts could not judge is listed under what the AI made of it", () => {
  const ai = { state: "done", reviews: { r1: { assessment: "likely_ok", finding: "the README explains the usage", by: "claude" } } };
  const t = tree({ results: mixed, ai });
  assert.deepEqual(t.labels(t.top()), ["Result: PASS", "AI review: done", "Failed (1)", "Warnings (1)", "Passed (3)"]);
  const passed = t.top().at(-1) as ReviewNode;
  const readme = t.childrenOf(passed).find((n) => n.item.label === "Readme") as ReviewNode;
  assert.deepEqual(t.labels(t.childrenOf(readme)), ["claude: likely ok"]);
  assert.match(String(t.childrenOf(readme)[0].item.tooltip), /AI-generated, unverified/);
  const unclear = tree({ results: mixed, ai: { state: "done", reviews: { r1: { assessment: "unclear", why_manual: "needs a person" } } } });
  assert.ok(unclear.labels(unclear.top()).includes("Needs manual review (1)"));
});

test("a check lists what it found: the file and line it cites, its log, and the PDF page it comes from", () => {
  const t = tree({ results: [aCheck({ title: "Norm", status: "fail", detail: "2 errors", evidence: [{ file: "src/a.c", line: 12, snippet: "int x;" }, { file: "b.h" }],
    log: "norminette output", sources: [{ pdf: "push_swap.pdf", page: 3 }, { pdf: "en.norm.pdf" }] })] });
  const group = t.top()[1];
  const [norm] = t.childrenOf(group);
  assert.equal(norm.item.description, "2 errors");
  assert.equal(norm.item.collapsibleState, 1);
  const rows = t.childrenOf(norm);
  assert.deepEqual(t.labels(rows), ["src/a.c:12", "b.h", "Show the log", "From push_swap.pdf, page 3", "From en.norm.pdf"]);
  const open = rows[0].item.command as unknown as { command: string; arguments: [{ fsPath: string }, { selection: { start: { line: number } } }] };
  assert.equal(open.command, "vscode.open");
  assert.equal(open.arguments[0].fsPath, path.join("/projects", "cub3d", "src", "a.c"));
  assert.equal(open.arguments[1].selection.start.line, 11, "the line is 1-based in the check, 0-based in the editor");
  assert.equal(rows[0].item.description, "int x;");
  assert.deepEqual(rows[2].item.command?.arguments, ["norminette output", "log"]);
  assert.deepEqual(rows[3].item.command, { command: "verdict.openSubject", title: "Open the PDF", arguments: ["push_swap.pdf", 3] });
});

test("a file a check cites outside the project is shown, but cannot be opened", () => {
  const t = tree({ results: [aCheck({ status: "fail", evidence: [{ file: "../../etc/passwd", line: 1 }] })] });
  const [check] = t.childrenOf(t.top()[1]);
  assert.equal(t.childrenOf(check)[0].item.command, undefined);
});

test("a check with a single thing under it opens it by itself; one with nothing is a leaf; a bonus is marked; at most four PDFs are listed", () => {
  const t = tree({ results: [aCheck({ title: "one", status: "fail", sources: [{ pdf: "a.pdf", page: 1 }] }), aCheck({ title: "none", status: "fail" }),
    aCheck({ title: "extra", status: "fail", section: "bonus", sources: Array.from({ length: 6 }, (_, i) => ({ pdf: `p${i}.pdf` })) })] });
  const [one, none, extra] = t.childrenOf(t.top()[1]);
  assert.equal(one.item.command?.command, "verdict.openSubject");
  assert.equal(none.item.collapsibleState, 0);
  assert.equal(none.item.command, undefined);
  assert.equal(extra.item.label, "extra [bonus]");
  assert.equal(t.childrenOf(extra).length, 4);
  assert.equal(extra.item.command, undefined, "several things: the person chooses");
});

test("a check made by claude says so in its tooltip", () => {
  const t = tree({ results: [aCheck({ title: "Leaks", status: "warn", detail: "3 bytes", by: "Claude" })] });
  const [check] = t.childrenOf(t.top()[1]);
  assert.equal((check.item.tooltip as { value: string }).value, "Leaks\n\n3 bytes\n\n(from claude's review)");
});
