import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import test from "node:test";
import { REPORT_NAME, ReportFile } from "../../../src/extension/report/report-file";
import { scratch } from "../support/harness";

test("claude's report is looked for in the folder of the session, under the name the terminal saves it with", () => {
  assert.equal(REPORT_NAME, "claude-review.md");
  assert.equal(new ReportFile("/scratch/reports").pathOf("s1"), path.join("/scratch/reports", "s1", "claude-review.md"));
});

test("the signature of a report changes when the file is saved again, and is null without a file", async () => {
  const root = scratch();
  const reports = new ReportFile(root);
  fs.mkdirSync(path.join(root, "s1"));
  assert.equal(await reports.signature("s1"), null);
  const file = path.join(root, "s1", REPORT_NAME);
  fs.writeFileSync(file, "one");
  const one = await reports.signature("s1");
  fs.writeFileSync(file, "two, longer");
  assert.notEqual(await reports.signature("s1"), one);
  assert.equal(await reports.signature("another-session"), null, "a session that saved nothing");
});

test("a folder is no report", async () => {
  const root = scratch();
  fs.mkdirSync(path.join(root, "s1", REPORT_NAME), { recursive: true });
  assert.equal(await new ReportFile(root).signature("s1"), null);
});
