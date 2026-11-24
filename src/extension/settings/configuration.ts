import * as vscode from "vscode";

/** The extension's own settings of the editor (the `verdict.*` entries of the manifest). */
export class Configuration {
  /** Open a JSON file that is hard to read as a pretty-printed, read-only view. */
  prettyJsonOnOpen(): boolean {
    return vscode.workspace.getConfiguration("verdict").get("json.prettyOnOpen", true);
  }
}
