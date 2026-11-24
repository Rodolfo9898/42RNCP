import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { MAX_BYTES } from "./pretty-json";

export const SCHEME = "verdict-json";

export const isJsonFile = (uri: vscode.Uri): boolean => uri.scheme === "file" && /\.json$/i.test(uri.path);

/** The text of a JSON file, or null when it cannot be read or is too big to be shown. */
export async function readJson(file: string): Promise<string | null> {
  try {
    if ((await fs.promises.stat(file)).size > MAX_BYTES) return null;
    return await fs.promises.readFile(file, "utf8");
  } catch {
    return null;
  }
}

/** The address of the pretty view of a file: its name says it is the pretty one, its query says which file it follows. */
export function viewUri(file: string): vscode.Uri {
  const name = path.basename(file).replace(/\.json$/i, "");
  return vscode.Uri.from({ scheme: SCHEME, path: `${path.dirname(file)}/${name} (pretty).json`, query: new URLSearchParams({ file }).toString() });
}

/** The file a pretty view follows (null when the address does not name a JSON file by an absolute path). */
export function fileOf(view: vscode.Uri): string | null {
  const file = new URLSearchParams(view.query).get("file");
  return file && path.isAbsolute(file) && /\.json$/i.test(file) ? file : null;
}
