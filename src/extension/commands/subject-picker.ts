import * as vscode from "vscode";
import type { Library } from "../api/types";

/** A line of the picker of library PDFs; `path` is the PDF's place in the library (the lines that are separators have none). */
export interface LibraryChoice extends vscode.QuickPickItem { path?: string }

const key = (name: string): string => name.toLowerCase().replace(/[^a-z0-9]/g, "");

/** The library as a picker: PDFs under the name of their track. A PDF already in the review comes ticked, and so does the project's
 * own subject (a PDF named like the project): Enter adds it. */
export function libraryChoices(lib: Library, have: Set<string>, projectName: string): LibraryChoice[] {
  const project = key(projectName);
  const matches = (name: string): boolean => !!project && key(name.replace(/\.pdf$/i, "")) === project;
  const choices: LibraryChoice[] = [];
  for (const track of lib.tracks) {
    const inTrack = lib.items.filter((item) => item.track === track.id);
    if (!inTrack.length) continue;
    choices.push({ label: track.label, kind: vscode.QuickPickItemKind.Separator });
    for (const item of inTrack) {
      choices.push({ label: item.name, description: have.has(item.name) ? "in this review" : matches(item.name) ? "this project's subject" : "",
        picked: have.has(item.name) || matches(item.name), path: item.path });
    }
  }
  return choices;
}
