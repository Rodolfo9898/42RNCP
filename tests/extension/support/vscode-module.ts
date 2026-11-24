import { FakeEditor } from "./fake-vscode";

/** The one fake editor of a test file. `require("vscode")` in the extension's code gives its API (the extension is compiled to
 * CommonJS, so the module is looked up here). Import this module BEFORE anything of the extension, and `editor.reset()` between tests. */
export const editor = new FakeEditor();

type Loader = (this: unknown, request: string, parent: unknown, isMain: boolean) => unknown;
const nodeModule = require("node:module") as { _load: Loader };
const load = nodeModule._load;
nodeModule._load = function (request, parent, isMain) {
  return request === "vscode" ? editor.api : load.call(this, request, parent, isMain);
};
