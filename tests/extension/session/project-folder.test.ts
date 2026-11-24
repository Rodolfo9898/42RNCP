import assert from "node:assert/strict";
import * as path from "node:path";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { ProjectFolder } from "../../../src/extension/session/project-folder";
import { SessionState } from "../../../src/extension/session/session-state";
import { aSession } from "../support/fixtures";

function folder(extra = {}) {
  editor.reset();
  const state = new SessionState();
  state.set(aSession(extra));
  return new ProjectFolder("/projects", state);
}

test("the project's folder is under the projects folder; without a project there is none", () => {
  assert.equal(folder().dir(), path.join("/projects", "cub3d"));
  assert.equal(folder({ repo: null }).dir(), null);
  assert.throws(() => folder({ repo: null }).require(), /open a project first/);
  assert.equal(new ProjectFolder("/projects", new SessionState()).dir(), null, "before any session");
});

test("a file of the project is an address, and nothing that leaves the project is (the paths come from the checks)", () => {
  const project = folder({ repo: { path: "rncp/cub3d", name: "cub3d" } });
  assert.equal(project.uri("src/main.c")?.fsPath, path.join("/projects", "rncp", "cub3d", "src", "main.c"));
  assert.equal(project.uri(".")?.fsPath, path.join("/projects", "rncp", "cub3d"));
  assert.equal(project.uri("../other/secret"), null);
  assert.equal(project.uri("../../../../etc/passwd"), null);
  assert.equal(project.uri("/etc/passwd"), null);
  assert.equal(project.uri("src/../../cub3d2/x"), null, "a sibling that starts with the same name");
  assert.equal(folder({ repo: null }).uri("main.c"), null);
});
