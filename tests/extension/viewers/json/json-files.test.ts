import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import test from "node:test";
import { editor } from "../../support/vscode-module";
import { scratch } from "../../support/harness";
import { fileOf, readJson, viewUri } from "../../../../src/extension/viewers/json/json-files";
import { MAX_BYTES } from "../../../../src/extension/viewers/json/pretty-json";

test("the pretty view of a file says in its name that it is the pretty one, and in its query which file it follows", () => {
  const view = viewUri("/projects/cub3d/maps/level8.json");
  assert.equal(view.scheme, "verdict-json");
  assert.equal(view.path, "/projects/cub3d/maps/level8 (pretty).json");
  assert.equal(fileOf(view), "/projects/cub3d/maps/level8.json");
});

test("an address that does not name a JSON file by an absolute path follows nothing", () => {
  for (const query of ["", "file=relative.json", "file=%2Ftmp%2Fnotes.txt"]) {
    assert.equal(fileOf(editor.api.Uri.from({ scheme: "verdict-json", path: "/x.json", query })), null, query);
  }
});

test("a JSON file is read unless it is missing or too big to be shown", async () => {
  const dir = scratch();
  const small = path.join(dir, "small.json");
  fs.writeFileSync(small, '{"a":1}');
  assert.equal(await readJson(small), '{"a":1}');
  assert.equal(await readJson(path.join(dir, "missing.json")), null);
  const big = path.join(dir, "big.json");
  fs.writeFileSync(big, "x".repeat(MAX_BYTES + 1));
  assert.equal(await readJson(big), null);
});
