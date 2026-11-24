import assert from "node:assert/strict";
import test from "node:test";
import { editor } from "../support/vscode-module";
import { ChannelLog } from "../../../src/extension/output/channel-log";

test("every line of a channel carries the time, and nothing empty is written", () => {
  editor.reset();
  const log = new ChannelLog(editor.api.window.createOutputChannel("x"));
  log.line("hello");
  log.line("");
  log.line(undefined);
  assert.equal(editor.calls.length, 1);
  assert.match(editor.calls[0][1] as string, /^\[\d\d:\d\d:\d\d\] hello$/);
});

test("a channel is shown with or without taking the focus, and is disposed with the extension", () => {
  editor.reset();
  const shown: Array<boolean | undefined> = [];
  let disposed = false;
  const log = new ChannelLog({ appendLine() {}, show: (preserveFocus?: boolean) => shown.push(preserveFocus), dispose: () => { disposed = true; } } as never);
  log.show(true);
  log.show();
  log.dispose();
  assert.deepEqual(shown, [true, undefined]);
  assert.equal(disposed, true);
});
