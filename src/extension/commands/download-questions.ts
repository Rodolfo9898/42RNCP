import * as vscode from "vscode";
import type { DownloadRequest } from "../api/types";

/** The tracks of the library (the folders of samples/), as the app names them. */
const TRACKS = [{ id: "common-core", label: "Common Core" }, { id: "post-common-core", label: "Post Common Core" }, { id: "rncp", label: "RNCP" }];

interface TrackChoice extends vscode.QuickPickItem { id: string }
interface ArtifactsChoice extends vscode.QuickPickItem { artifacts: boolean }

/** The two questions before a download: which tracks, and whether the artifacts (the files some projects come with) come too. The
 * rest of the request is fixed: the projects inside a piscine or a series come too, and a PDF already in the library is kept.
 * Undefined when the person gives up. */
export async function askDownload(): Promise<DownloadRequest | undefined> {
  const tracks = await vscode.window.showQuickPick<TrackChoice>(TRACKS.map((track) => ({ ...track, picked: true })),
    { canPickMany: true, title: "Download subjects from the intra", placeHolder: "Which tracks?" });
  if (!tracks?.length) return undefined;
  const kind = await vscode.window.showQuickPick<ArtifactsChoice>([
    { label: "Subjects and artifacts", artifacts: true },
    { label: "Subjects only (artifacts can be gigabytes)", artifacts: false }],
    { title: "Download subjects from the intra", placeHolder: "What to download?" });
  if (!kind) return undefined;
  return { tracks: tracks.map((track) => track.id), projects: null, artifacts: kind.artifacts, children: true, force: false };
}
