import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { Configuration } from "../../../src/extension/settings/configuration";

test("the JSON view is on unless the person turned it off in the editor's settings", () => {
  editor.reset();
  assert.equal(new Configuration().prettyJsonOnOpen(), true);
  editor.settings["verdict.json.prettyOnOpen"] = false;
  assert.equal(new Configuration().prettyJsonOnOpen(), false);
});
