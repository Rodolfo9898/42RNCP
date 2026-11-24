import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

/** The repository's root, found from wherever the tests were compiled to. */
function findRoot(): string {
  let dir = __dirname;
  while (!fs.existsSync(path.join(dir, "pyproject.toml"))) {
    const parent = path.dirname(dir);
    if (parent === dir) throw new Error("the repository root was not found");
    dir = parent;
  }
  return dir;
}

export const ROOT = findRoot();
export const EXTENSION_DIR = path.join(ROOT, "src", "extension");

export const scratch = (): string => fs.mkdtempSync(path.join(os.tmpdir(), "verdict-ext-"));
export const pause = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** Waits (real time) until `condition` holds, or fails the test saying what never happened. */
export async function until(condition: () => boolean, what: string, tenths = 200): Promise<void> {
  for (let i = 0; i < tenths; i++) {
    if (condition()) return;
    await pause(10);
  }
  assert.fail(`never happened: ${what}`);
}
