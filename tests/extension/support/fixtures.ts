import type { CheckResult, MergeAnswer, SessionView } from "../../../src/extension/api/types";

/** A finished review of the project cub3d, with one check passed: the base the tests change. */
export function aSession(extra: Partial<SessionView> = {}): SessionView {
  return {
    id: "s1", state: "done", message: "", repo: { path: "cub3d", name: "cub3d", commit: "abc1234" }, subjects: [],
    results: [{ title: "t", status: "pass" }], summary: { overall: "PASS" }, ai: { state: "idle" }, verdict_file: "verdict.md", ...extra,
  };
}

export const aCheck = (extra: Partial<CheckResult> = {}): CheckResult => ({ title: "a check", status: "pass", ...extra });

/** What `PUT claude-review` answers for a report that was merged. */
export function aMerge(extra: Partial<MergeAnswer> = {}): MergeAnswer {
  return {
    new: true, written: true, stale: false, structured: true, assessed: 3, total: 4, verdict_file: "verdict.md", problems: [], source_name: "claude-review.md",
    warning: "", ...extra,
  };
}
