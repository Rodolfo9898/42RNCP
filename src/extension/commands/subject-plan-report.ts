import type { IntraSession, LibraryPlan, TrackPlan } from "../api/types";
import { plural } from "./wording";

/** What the person does to be able to download: the login to the intra is made once, on the computer that has the browser (not here). */
const LOGIN_FIX = "run `make samples-login` on your computer";

export const missingSubjects = (plan: LibraryPlan): number => plan.tracks.reduce((sum, track) => sum + track.missing.length, 0);

function trackLines(track: TrackPlan): string[] {
  const head = `${track.label}: ${plural(track.total, "subject")}, ${track.with_pdf} with a PDF, ${track.missing.length} missing`;
  return [head, ...track.missing.map((subject) => `  - ${subject.name}`)];
}

function sessionLines({ valid, reason }: IntraSession): string[] {
  if (valid) return ["The saved login to the intra can be used."];
  return [`The saved login to the intra cannot be used${reason ? `: ${reason}` : "."}`, `To download: ${LOGIN_FIX}.`];
}

/** The plan as the text of the "Verdict: Subjects" channel: per track what is there and what is missing, the names the intra lists
 * that no track has, how many files are not in the folder of their series, and whether the saved login to the intra can be used. */
export function planReport(plan: LibraryPlan): string[] {
  const lines = ["Subjects of the library against the intra", ...sessionLines(plan.session)];
  for (const track of plan.tracks) lines.push("", ...trackLines(track));
  if (plan.unknown.length) lines.push("", `In no track: ${plan.unknown.join(", ")}`);
  if (plan.misplaced) lines.push("", `${plan.misplaced} not in the folder of their series: run "Verdict: File Subjects in Their Series Folders".`);
  return lines;
}

/** The one line shown to the person: how much is missing, how many files are out of place, and the login when it is what stops a download. */
export function planMessage(plan: LibraryPlan): string {
  const missing = missingSubjects(plan);
  const tracks = plan.tracks.filter((track) => track.missing.length).length;
  return [
    missing ? `${plural(missing, "subject")} missing in ${plural(tracks, "track")}` : "Nothing missing",
    plan.misplaced ? `${plan.misplaced} not filed in their series folder` : "",
    missing && !plan.session.valid ? `the saved login to the intra cannot be used: ${LOGIN_FIX}` : "",
  ].filter(Boolean).join("; ");
}
