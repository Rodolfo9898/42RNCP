import * as fs from "node:fs";
import * as path from "node:path";

export const REPORT_NAME = "claude-review.md";

type Stat = (file: string) => Promise<{ isFile(): boolean; mtimeMs: number; size: number }>;

/** Where claude saves its report: <root>/<session>/claude-review.md, outside the project (the terminal service reads the same file). */
export class ReportFile {
  constructor(private readonly root: string, private readonly stat: Stat = fs.promises.stat) {}

  pathOf(sid: string): string { return path.join(this.root, sid, REPORT_NAME); }

  /** "mtime:size" of the report, or null when it is not there. */
  async signature(sid: string): Promise<string | null> {
    try {
      const st = await this.stat(this.pathOf(sid));
      return st.isFile() ? `${st.mtimeMs}:${st.size}` : null;
    } catch {
      return null;
    }
  }
}
