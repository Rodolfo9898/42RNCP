import type { DownloadStatus, DownloadSummary } from "../api/types";
import { plural } from "./wording";

const counts = (s: DownloadSummary): string => `Downloaded ${plural(s.downloaded_subjects, "subject")} and ${plural(s.downloaded_artifacts, "artifact")}`;

/** What the person is told when the download ended: the counts, and where to look when some projects failed or had no files. */
export function downloadMessage({ state, summary }: DownloadStatus): string {
  if (state === "idle") return "No download is running.";
  if (!summary) return state === "cancelled" ? "The download was stopped." : "The download is done.";
  const problems = summary.failed.length + summary.no_files.length;
  const text = problems ? `${counts(summary)}; ${problems} failed or without files: see the Verdict: Subjects output` : counts(summary);
  return state === "cancelled" ? `The download was stopped. ${text}` : text;
}

/** The end of the download for the channel: the counts, and the names of the projects that failed or came without files. */
export function summaryLines(summary: DownloadSummary): string[] {
  const lines = [`${counts(summary)}; ${summary.existing} already in the library.`];
  if (summary.failed.length) lines.push(`Failed: ${summary.failed.join(", ")}`);
  if (summary.no_files.length) lines.push(`Without files: ${summary.no_files.join(", ")}`);
  return lines;
}
