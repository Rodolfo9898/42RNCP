import * as vscode from "vscode";
import type { AiAssessment, AiState, CheckResult } from "../api/types";

/** The groups of the Review view, worst first, and how each is named. */
export const ORDER = ["fail", "warn", "manual", "skipped", "na", "pass"];
export const TITLES: Record<string, string> = {
  fail: "Failed", warn: "Warnings", manual: "Needs manual review", skipped: "Not checked", na: "Not applicable", pass: "Passed",
};
const ICONS: Record<string, [string, string | undefined]> = {
  fail: ["error", "errorForeground"], warn: ["warning", "editorWarning.foreground"], manual: ["question", "editorInfo.foreground"],
  skipped: ["dash", undefined], na: ["circle-slash", undefined], pass: ["pass", "testing.iconPassed"],
};
const REVIEWED_STATUS: Record<string, string> = { likely_problem: "fail", unclear: "manual", likely_ok: "pass", not_applicable: "pass" };

/** What the AI said about a check, if it was asked. */
export function assessmentOf(result: CheckResult, ai: AiState): AiAssessment | undefined {
  return result.rule_id ? ai.reviews?.[result.rule_id] : undefined;
}

/** The status a check is listed under: a check the scripts could not judge counts as what the AI made of it. */
export function shownStatus(result: CheckResult, ai: AiState): string {
  const review = result.status === "manual" ? assessmentOf(result, ai) : undefined;
  return review ? (REVIEWED_STATUS[review.assessment] ?? "manual") : result.status;
}

export function themedIcon(status: string): vscode.ThemeIcon {
  const [id, color] = ICONS[status] ?? ["circle-outline", undefined];
  return new vscode.ThemeIcon(id, color ? new vscode.ThemeColor(color) : undefined);
}
