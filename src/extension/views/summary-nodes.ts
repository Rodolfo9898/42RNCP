import * as vscode from "vscode";
import type { AiState, SessionView } from "../api/types";
import type { ReviewNode } from "./review-node";
import { ORDER, TITLES, shownStatus, themedIcon } from "./check-status";
import type { CheckNodeBuilder } from "./check-nodes";

/** The top of the Review view: the result, the AI review when there is one, then the checks grouped by status. */
export function resultNode(view: SessionView, busy: boolean): ReviewNode {
  const summary = view.summary;
  const ran = view.results.length > 0;
  const item = new vscode.TreeItem(ran ? `Result: ${summary.overall}` : (busy ? "Running…" : "Not run yet"));
  item.description = ran ? (summary.decided_by === "claude" ? "decided by claude" : "from the checks") : "Run the checks";
  item.tooltip = summary.reason || (ran ? "FAIL when anything is lacking, PASS WITH ISSUES when something needs a second look, PASS otherwise." : "");
  item.iconPath = new vscode.ThemeIcon(busy ? "sync~spin" : "shield");
  if (!ran && !busy) item.command = { command: "verdict.runChecks", title: "Run Checks" };
  return { item };
}

export function aiNode(ai: AiState): ReviewNode | null {
  if (!ai.state || ai.state === "idle") return null;
  const item = new vscode.TreeItem(`AI review: ${ai.state}`);
  item.description = ai.message || "";
  item.iconPath = new vscode.ThemeIcon(ai.state === "running" ? "sync~spin" : "sparkle");
  item.command = { command: "verdict.showAiLog", title: "Show the AI's log" };
  return { item };
}

export function groupNodes(view: SessionView, checks: CheckNodeBuilder): ReviewNode[] {
  const groups: ReviewNode[] = [];
  for (const status of ORDER) {
    const results = view.results.filter((r) => shownStatus(r, view.ai) === status);
    if (!results.length) continue;
    const quiet = status === "pass" || status === "na";
    const item = new vscode.TreeItem(`${TITLES[status]} (${results.length})`,
      quiet ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.Expanded);
    item.iconPath = themedIcon(status);
    groups.push({ item, children: () => results.map((r) => checks.build(r, view.ai)) });
  }
  return groups;
}
