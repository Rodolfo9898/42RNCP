import * as path from "node:path";
import * as vscode from "vscode";
import type { SessionState } from "./session-state";

/** The folder of the project under review, inside the projects folder. */
export class ProjectFolder {
  constructor(readonly projectsDir: string, private readonly session: SessionState) {}

  dir(): string | null {
    const repo = this.session.current?.repo;
    return repo?.path ? path.join(this.projectsDir, repo.path) : null;
  }

  /** The folder, for what cannot go on without one. */
  require(): string {
    const dir = this.dir();
    if (!dir) throw new Error("open a project first");
    return dir;
  }

  /** A file of the project, as an address; null for anything that would leave the project (the paths come from untrusted checks). */
  uri(file: string): vscode.Uri | null {
    const root = this.dir();
    if (!root) return null;
    const full = path.resolve(root, file);
    return full === root || full.startsWith(root + path.sep) ? vscode.Uri.file(full) : null;
  }
}
