import assert from "node:assert/strict";
import test from "node:test";
import { ReportWatcher } from "../../../src/extension/report/report-watcher";
import { until } from "../support/harness";

test("a report is collected once it has stopped changing, once per version, and again when claude saves a new one", async () => {
  let file: string | null = null;
  const collected: Array<string | null> = [];
  const heard: Array<{ new: boolean }> = [];
  const watch = new ReportWatcher(async () => file, async () => { collected.push(file); return { new: true }; }, (r) => heard.push(r));
  await watch.tick();                                        // no report yet
  file = "v1";
  await watch.tick();                                        // seen for the first time: it may still be being written
  assert.deepEqual(collected, []);
  file = "v1b";
  await watch.tick();                                        // changed again
  assert.deepEqual(collected, []);
  await watch.tick();                                        // the same twice: collect
  assert.deepEqual(collected, ["v1b"]);
  await watch.tick(); await watch.tick();
  assert.deepEqual(collected, ["v1b"], "not again while it is the same");
  file = "v2";                                               // the next pass of claude's review
  await watch.tick(); await watch.tick();
  assert.deepEqual(collected, ["v1b", "v2"]);
  assert.equal(heard.length, 2);
});

test("a report that goes away and comes back is collected again", async () => {
  let file: string | null = "v1";
  let collects = 0;
  const watch = new ReportWatcher(async () => file, async () => { collects++; return {}; }, () => {});
  await watch.tick(); await watch.tick();
  file = null;
  await watch.tick();
  file = "v1";
  await watch.tick(); await watch.tick();
  assert.equal(collects, 1, "the same version is not collected twice, even after the file was gone for a moment");
});

test("a collect that fails is tried again on the next look, and two looks never overlap", async () => {
  let attempts = 0;
  let release: () => void = () => {};
  const heard: unknown[] = [];
  const watch = new ReportWatcher(
    async () => "v1",
    (): Promise<{ new: boolean }> => { attempts++; if (attempts === 1) throw new Error("the app is down"); return new Promise((resolve) => { release = () => resolve({ new: true }); }); },
    (r) => heard.push(r));
  await watch.tick();
  await watch.tick();                                        // collect throws
  assert.equal(attempts, 1);
  const slow = watch.tick();                                 // collect starts and waits
  await until(() => attempts === 2, "the second attempt");
  await watch.tick();                                        // overlapping: ignored
  assert.equal(attempts, 2);
  release();
  await slow;
  assert.equal(heard.length, 1);
  await watch.tick();
  assert.equal(attempts, 2, "done");
});
