"use strict";

// Picking up claude's report. claude saves it (claude-review.md, outside the project) at the end of each pass of its review: the
// first one, and every fix-and-update after it. This looks at that file and, each time it has changed and stopped changing, asks
// the app to merge it into verdict.md. No vscode here: the pieces come in as functions, so it can be tested on its own.

const REPORT_NAME = "claude-review.md";

// "mtime:size" of the report, or null when it is not there.
async function signature(stat, file) {
  try {
    const st = await stat(file);
    return st.isFile() ? `${st.mtimeMs}:${st.size}` : null;
  } catch {
    return null;
  }
}

// `look()` gives the signature now, `collect()` asks the app to merge (it throws when it cannot), `done(result)` hears the answer.
// `tick()` is called every couple of seconds. A report is collected once it looks the same on two ticks in a row (a write in
// progress is not read half done), and once per version: a failed collect is tried again on the next tick.
function watcher({ look, collect, done }) {
  let previous = null;
  let handled = null;
  let running = false;
  return {
    async tick() {
      if (running) return;
      running = true;
      try {
        const now = await look();
        if (now === null || now !== previous) { previous = now; return; }
        if (now === handled) return;
        const result = await collect();
        handled = now;
        done(result);
      } catch {
        /* the app or the file is not ready: the next tick tries again */
      } finally {
        running = false;
      }
    },
  };
}

module.exports = { REPORT_NAME, signature, watcher };
