import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../../support/vscode-module";
import { SessionState } from "../../../../src/extension/session/session-state";
import { MAX_PAGES, PdfViewer } from "../../../../src/extension/viewers/pdf/pdf-viewer";
import { aSession } from "../../support/fixtures";

function subjects() {
  editor.reset();
  const state = new SessionState();
  const set = (names: Array<[string, string, number]>) => state.set(aSession({ subjects: names.map(([name, kind, pages]) => ({ name, kind, pages, rules: [] })) }));
  set([["push_swap.pdf", "subject", 12], ["en.norm.pdf", "norm", 3]]);
  const asked: Array<[string, number]> = [];
  const fetching = { failing: false };
  const viewer = new PdfViewer(state, async (name, n) => {
    asked.push([name, n]);
    if (fetching.failing) throw new Error("HTTP 404");
    return Buffer.from(`png-${name}-${n}`);
  });
  viewer.register();
  const subjectsOf = () => state.require().subjects;
  return { state, viewer, asked, fetching, subjectsOf, open: (...args: unknown[]) => editor.run("verdict.openSubject", ...args),
    replaceSubjects: (names: Array<[string, string, number]>) => set(names) };
}

test("a subject opens in a tab of its own, in the editor's active column, with the scripts allowed and no local resources", async () => {
  const run = subjects();
  await run.open("push_swap.pdf");
  assert.equal(editor.panels.length, 1);
  const panel = editor.panels[0];
  assert.equal(panel.title, "push_swap.pdf");
  assert.equal(panel.viewType, "verdict.subject");
  assert.deepEqual(panel.options, { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [] });
  assert.match(panel.webview.html, /"pages":12/);
  assert.match(panel.webview.html, /"page":1/);
  const nonce = (panel.webview.html.match(/script-src 'nonce-([0-9a-f]{32})'/) as RegExpMatchArray)[1];
  await run.open("en.norm.pdf");
  assert.ok(!editor.panels[1].webview.html.includes(nonce), "a nonce of its own for every tab");
});

test("the pages are sent one by one, as images, and only the pages that exist are answered", async () => {
  const run = subjects();
  await run.open("push_swap.pdf");
  const panel = editor.panels[0];
  await panel.say({ t: "page", n: 3 });
  assert.deepEqual(run.asked, [["push_swap.pdf", 3]]);
  assert.deepEqual(panel.posted, [{ t: "page", n: 3, src: `data:image/png;base64,${Buffer.from("png-push_swap.pdf-3").toString("base64")}` }]);
  for (const bad of [{ t: "page", n: 0 }, { t: "page", n: 13 }, { t: "page", n: 1.5 }, { t: "page", n: "2" }, { t: "other", n: 1 }, null, "page", { n: 2 }]) await panel.say(bad);
  assert.equal(run.asked.length, 1, "nothing else was fetched");
  run.fetching.failing = true;
  await panel.say({ t: "page", n: 4 });
  assert.deepEqual(panel.posted.at(-1), { t: "error", n: 4, text: "HTTP 404" });
});

test("opening a PDF again goes to its tab at the page asked for, never past its last page", async () => {
  const run = subjects();
  await run.open("push_swap.pdf", 5);
  assert.match(editor.panels[0].webview.html, /"page":5/);
  await run.open("push_swap.pdf", 7);
  await run.open("push_swap.pdf", 99);
  await run.open("push_swap.pdf", "x");
  assert.equal(editor.panels.length, 1);
  assert.equal(editor.panels[0].revealed, 3);
  assert.deepEqual(editor.panels[0].posted.map((m) => (m as { page: number }).page), [7, 12, 1]);
  await run.open({ subject: "en.norm.pdf" });                       // from the Subjects view, the item itself is the argument
  assert.deepEqual(editor.panels.map((p) => p.title), ["push_swap.pdf", "en.norm.pdf"]);
});

test("a PDF that is not a subject of the review is explained, and a tab of a removed subject is closed", async () => {
  const run = subjects();
  await run.open("nothing.pdf");
  await run.open(undefined);
  assert.equal(editor.panels.length, 0);
  assert.deepEqual(editor.messages.error, ["Verdict: nothing.pdf is not a subject of this review", "Verdict: that PDF is not a subject of this review"]);
  run.replaceSubjects([["push_swap.pdf", "subject", 12], ["en.norm.pdf", "norm", 3], ["empty.pdf", "subject", 0]]);
  await run.open("empty.pdf");
  assert.match(editor.messages.error.at(-1) as string, /has no pages to show/);
  await run.open("push_swap.pdf");
  run.replaceSubjects([["en.norm.pdf", "norm", 3], ["empty.pdf", "subject", 0]]);
  run.viewer.sync();
  assert.equal(editor.panels[0].disposed, true);
  await run.open("en.norm.pdf");
  editor.panels[1].dispose();                                       // closed by the person: opening it again makes a new tab
  await run.open("en.norm.pdf");
  assert.equal(editor.panels.length, 3);
});

test("a very long PDF is not turned into thousands of page boxes", async () => {
  const run = subjects();
  run.replaceSubjects([["huge.pdf", "subject", 100000]]);
  await run.open("huge.pdf");
  assert.match(editor.panels[0].webview.html, new RegExp(`"pages":${MAX_PAGES}`));
});
