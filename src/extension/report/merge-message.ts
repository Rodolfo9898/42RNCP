import type { MergeAnswer } from "../api/types";

/** What a merge did, in words. */
export function describeMerge(r: MergeAnswer): string {
  const file = r.verdict_file || "verdict.md";
  if (!r.structured) return `claude's report was added to ${file} as text: it has no data block at the end, so it could not be merged into the lists. ${(r.problems || [])[0] || ""}`.trim();
  return `Merged claude's answers (${r.assessed} of ${r.total} requirements) into ${file}.${r.assessed < r.total ? ` ${r.total - r.assessed} requirement(s) were not answered.` : ""}`;
}
