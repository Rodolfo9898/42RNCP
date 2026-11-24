import assert from "node:assert/strict";
import test from "node:test";
import { readSettings } from "../../../src/extension/settings/environment";

test("without anything set the extension looks for the web app, the projects and claude's reports where the containers put them", () => {
  assert.deepEqual(readSettings({}), { apiUrl: "http://web:8000", projectsDir: "/projects", reportsRoot: "/scratch/reports" });
});

test("what the environment sets is used, and a slash at the end of a URL or a folder is dropped", () => {
  const settings = readSettings({ VERDICT_API: "http://localhost:8000/", PROJECTS_DIR: "/work/projects", REPORTS_ROOT: "/tmp/reports/" });
  assert.deepEqual(settings, { apiUrl: "http://localhost:8000", projectsDir: "/work/projects", reportsRoot: "/tmp/reports" });
});
