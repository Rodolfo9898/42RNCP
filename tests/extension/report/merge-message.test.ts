import assert from "node:assert/strict";
import test from "node:test";
import { describeMerge } from "../../../src/extension/report/merge-message";
import { aMerge } from "../support/fixtures";

test("a merge says how many requirements claude answered and where", () => {
  assert.equal(describeMerge(aMerge()), "Merged claude's answers (3 of 4 requirements) into verdict.md. 1 requirement(s) were not answered.");
  assert.equal(describeMerge(aMerge({ assessed: 4 })), "Merged claude's answers (4 of 4 requirements) into verdict.md.");
  assert.match(describeMerge(aMerge({ verdict_file: null })), /into verdict\.md\./, "the usual name when the app gave none");
});

test("a report without its data block is said to be only text, with the first problem found", () => {
  const text = describeMerge(aMerge({ structured: false, problems: ["no data block at the end"] }));
  assert.equal(text, "claude's report was added to verdict.md as text: it has no data block at the end, so it could not be merged into the lists. no data block at the end");
  assert.ok(!describeMerge(aMerge({ structured: false })).endsWith(" "), "nothing dangles when there is no problem to quote");
});
