import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { FakeDownloads, aSummary } from "../support/fake-downloads";
import { until } from "../support/harness";
import { running } from "../support/running";
import type { Running } from "../support/running";

const SUBJECTS = "Verdict: Subjects";
const CURRENT = "GET library/downloads/current";
const STOP = "DELETE library/downloads/current";
const BUSY = "a download is already running";
type Pick = { label: string; id?: string; picked?: boolean; artifacts?: boolean };
type Answer = (items: unknown, options: unknown) => unknown;

const manyOf = (options: unknown): boolean => !!(options as { canPickMany?: boolean }).canPickMany;

/** The person ticks these tracks (by id) and picks whether the artifacts come too. */
const answers = (ids: string[], artifacts: boolean): Answer => (items, options) =>
  manyOf(options) ? (items as Pick[]).filter((i) => ids.includes(i.id as string)) : (items as Pick[]).find((i) => i.artifacts === artifacts);

const everything = (): Answer => answers(["common-core", "post-common-core", "rncp"], true);
const polls = (run: Running): string[] => run.app.callsTo(CURRENT).map((r) => r.route);

/** Starts the command and waits until the extension has asked the app about the download once (it is being followed); `finished` is
 * the command's own promise, which only ends with the download. */
async function started(run: Running): Promise<{ finished: Promise<unknown> }> {
  const finished = editor.run("verdict.subjectsDownload");
  await until(() => run.app.callsTo(CURRENT).length >= 1, "the first look at the download");
  return { finished };
}

test("it asks which tracks (all ticked) and whether the artifacts come, and starts the download with the answers", async () => {
  const run = await running();
  try {
    const service = new FakeDownloads(run.app);
    editor.answers.quickPick = answers(["common-core", "rncp"], false);
    service.end("done", aSummary());
    await editor.run("verdict.subjectsDownload");
    const [tracks, kind] = editor.calls.filter((c) => c[0] === "quickPick") as Array<[string, Pick[], { canPickMany?: boolean }]>;
    assert.deepEqual(tracks[1].map((i) => [i.label, i.id, i.picked]), [["Common Core", "common-core", true], ["Post Common Core", "post-common-core", true], ["RNCP", "rncp", true]]);
    assert.equal(tracks[2].canPickMany, true);
    assert.deepEqual(kind[1].map((i) => [i.label, i.artifacts]), [["Subjects and artifacts", true], ["Subjects only (artifacts can be gigabytes)", false]]);
    assert.deepEqual(run.app.calls("POST library/downloads").map((r) => r.body), [
      { tracks: ["common-core", "rncp"], projects: null, artifacts: false, children: true, force: false }]);
  } finally { run.stop(); }
});

test("nothing starts when the person gives up, ticks no track, or leaves the second question", async () => {
  const run = await running();
  try {
    new FakeDownloads(run.app);
    await editor.run("verdict.subjectsDownload");
    editor.answers.quickPick = (_items, options) => (manyOf(options) ? [] : undefined);
    await editor.run("verdict.subjectsDownload");
    editor.answers.quickPick = (items, options) => (manyOf(options) ? items : undefined);
    await editor.run("verdict.subjectsDownload");
    assert.equal(run.app.calls("POST library/downloads").length, 0);
    assert.equal(run.app.callsTo(CURRENT).length, 0);
  } finally { run.stop(); }
});

test("the download is followed in a notification every 2 seconds: each line of the app is written once, and it stops at done", async () => {
  const run = await running();
  try {
    const service = new FakeDownloads(run.app);
    editor.answers.quickPick = everything();
    service.say("cpp00: downloaded", "cpp01: downloaded");
    const { finished } = await started(run);
    assert.deepEqual((editor.calls.find((c) => c[0] === "progress") as unknown[])[1], { location: 15, title: "Downloading subjects from the intra…", cancellable: true });
    assert.deepEqual(editor.calls.filter((c) => c[0] === "show"), [["show", SUBJECTS, true]], "the channel is shown without taking the focus");
    service.say("cpp02: downloaded");
    await run.ticks(1);
    await run.ticks(1);                                                           // (nothing new this time)
    service.say("cpp03: no files");
    service.end("done", aSummary());
    await run.ticks(1);
    await finished;
    assert.deepEqual(polls(run).map((route) => route.split("?")[1]), ["since=0", "since=2", "since=3", "since=3"], "each time from where it stopped reading");
    assert.deepEqual(editor.output(SUBJECTS), ["cpp00: downloaded", "cpp01: downloaded", "cpp02: downloaded", "cpp03: no files",
      "Downloaded 12 subjects and 30 artifacts; 5 already in the library."]);
    assert.deepEqual(editor.messages.information, ["Downloaded 12 subjects and 30 artifacts"]);
    const shown = editor.calls.filter((c) => c[0] === "progressReport").map((c) => (c[1] as { message: string }).message);
    assert.deepEqual(shown, ["cpp01: downloaded", "cpp02: downloaded", "cpp03: no files"], "the notification shows the last line it got");
    await run.ticks(3);
    assert.equal(polls(run).length, 4, "it stopped asking");
  } finally { run.stop(); }
});

test("the end says how many projects failed or had no files, and the output names them", async () => {
  const run = await running();
  try {
    const service = new FakeDownloads(run.app);
    editor.answers.quickPick = everything();
    service.end("done", aSummary({ failed: ["a", "b", "c"], no_files: Array.from({ length: 38 }, (_, i) => `p${i}`) }));
    await editor.run("verdict.subjectsDownload");
    assert.deepEqual(editor.messages.information, ["Downloaded 12 subjects and 30 artifacts; 41 failed or without files: see the Verdict: Subjects output"]);
    const log = editor.output(SUBJECTS);
    assert.equal(log[1], "Failed: a, b, c");
    assert.match(log[2], /^Without files: p0, p1, .*, p37$/);
  } finally { run.stop(); }
});

test("a download that failed is shown as an error, and what the app printed stays in the output", async () => {
  const run = await running();
  try {
    const service = new FakeDownloads(run.app);
    editor.answers.quickPick = everything();
    service.say("the intra said no");
    service.end("failed");
    await editor.run("verdict.subjectsDownload");
    assert.deepEqual(editor.messages.error, ["Verdict: the download failed: see the Verdict: Subjects output"]);
    assert.deepEqual(editor.messages.information, []);
    assert.deepEqual(editor.output(SUBJECTS), ["the intra said no"]);
  } finally { run.stop(); }
});

test("a download the app stopped is told as stopped, with what it had got", async () => {
  const run = await running();
  try {
    const service = new FakeDownloads(run.app);
    editor.answers.quickPick = everything();
    service.end("cancelled", aSummary({ downloaded_subjects: 3, downloaded_artifacts: 0 }));
    await editor.run("verdict.subjectsDownload");
    assert.deepEqual(editor.messages.information, ["The download was stopped. Downloaded 3 subjects and 0 artifacts"]);
  } finally { run.stop(); }
});

test("Cancel on the notification asks the app to stop, once, and the following goes on until the app says it stopped", async () => {
  const run = await running();
  try {
    const service = new FakeDownloads(run.app);
    editor.answers.quickPick = everything();
    const { finished } = await started(run);
    assert.equal(run.app.calls(STOP).length, 0);
    editor.cancelProgress();
    await until(() => run.app.calls(STOP).length === 1, "the request to stop");
    service.say("cpp05: downloaded");                                              // (the app finishes the project it is on)
    await run.ticks(1);
    assert.deepEqual(editor.output(SUBJECTS), ["Stopping after the project in progress…", "cpp05: downloaded"]);
    service.end("cancelled", aSummary({ downloaded_subjects: 6 }));
    await run.ticks(1);
    await finished;
    assert.equal(run.app.calls(STOP).length, 1);
    assert.match(editor.messages.information[0], /^The download was stopped\. Downloaded 6 subjects/);
  } finally { run.stop(); }
});

test("a stop the app cannot do is written in the output, and the download is still followed", async () => {
  const run = await running();
  try {
    const service = new FakeDownloads(run.app);
    run.app.on(STOP, { detail: "the download service is not reachable" }, 503);
    editor.answers.quickPick = everything();
    const { finished } = await started(run);
    editor.cancelProgress();
    await until(() => editor.output(SUBJECTS).length === 2, "the failure to stop");
    assert.equal(editor.output(SUBJECTS)[1], "The download could not be stopped: the download service is not reachable");
    service.end("done", aSummary());
    await run.ticks(1);
    await finished;
    assert.deepEqual(editor.messages.error, []);
  } finally { run.stop(); }
});

test("a login that cannot be used is refused with the app's words (no stack), and nothing is followed", async () => {
  const run = await running();
  try {
    const detail = "the saved session of the intra cannot be used: run `make samples-login` on your computer";
    new FakeDownloads(run.app);
    run.app.on("POST library/downloads", { detail }, 400);
    editor.answers.quickPick = everything();
    await editor.run("verdict.subjectsDownload");
    assert.deepEqual(editor.messages.error, [`Verdict: ${detail}`]);
    assert.equal(run.app.callsTo(CURRENT).length, 0);
    assert.equal(editor.calls.filter((c) => c[0] === "progress").length, 0);
    assert.deepEqual(editor.output(SUBJECTS), []);
  } finally { run.stop(); }
});

test("a download is already running: the person is told, and that one is followed from its first line", async () => {
  const run = await running();
  try {
    const service = new FakeDownloads(run.app);
    run.app.on("POST library/downloads", { detail: BUSY }, 409);
    editor.answers.quickPick = everything();
    service.say("cpp00: downloaded");
    service.end("done", aSummary());
    await editor.run("verdict.subjectsDownload");
    assert.deepEqual(editor.messages.error, []);
    assert.deepEqual(editor.messages.information, ["A download is already running: following it.", "Downloaded 12 subjects and 30 artifacts"]);
    assert.equal(editor.output(SUBJECTS)[0], "cpp00: downloaded");
  } finally { run.stop(); }
});

test("a service that is not reachable is shown as an error", async () => {
  const run = await running();
  try {
    new FakeDownloads(run.app);
    run.app.on("POST library/downloads", { detail: "the download service is not reachable" }, 503);
    editor.answers.quickPick = everything();
    await editor.run("verdict.subjectsDownload");
    assert.deepEqual(editor.messages.error, ["Verdict: the download service is not reachable"]);
  } finally { run.stop(); }
});

test("when the app cannot be asked during the download the following ends with the error, and the timer is released", async () => {
  const run = await running();
  try {
    const service = new FakeDownloads(run.app);
    editor.answers.quickPick = everything();
    const { finished } = await started(run);
    run.app.on(CURRENT, { detail: "the download service is not reachable" }, 503);
    await run.ticks(1);
    await finished;
    assert.deepEqual(editor.messages.error, ["Verdict: the download service is not reachable"]);
    const asked = polls(run).length;
    service.end("done");
    await run.ticks(3);
    assert.equal(polls(run).length, asked);
  } finally { run.stop(); }
});

test("an app that says no download is running (idle) ends the following with that", async () => {
  const run = await running();
  try {
    new FakeDownloads(run.app).end("idle");
    editor.answers.quickPick = everything();
    run.app.on("POST library/downloads", { detail: BUSY }, 409);
    await editor.run("verdict.subjectsDownload");
    assert.equal(editor.messages.information.at(-1), "No download is running.");
  } finally { run.stop(); }
});
