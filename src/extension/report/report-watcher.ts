// Picking up claude's report. claude saves it (claude-review.md, outside the project) at the end of each pass of its review: the
// first one, and every fix-and-update after it. This looks at that file and, each time it has changed and stopped changing, asks
// the app to merge it into verdict.md. No vscode here: the pieces come in as functions, so it can be tested on its own.

/** `look()` gives the signature of the report now, `collect()` asks the app to merge (it throws when it cannot), `done(result)` hears the
 * answer. `tick()` is called every couple of seconds. A report is collected once it looks the same on two ticks in a row (a write in
 * progress is not read half done), and once per version: a failed collect is tried again on the next tick. */
export class ReportWatcher<Result> {
  private previous: string | null = null;
  private handled: string | null = null;
  private running = false;

  constructor(private readonly look: () => Promise<string | null>, private readonly collect: () => Promise<Result>,
    private readonly done: (result: Result) => void) {}

  async tick(): Promise<void> {
    if (this.running) return;
    this.running = true;
    try {
      const now = await this.look();
      if (now === null || now !== this.previous) { this.previous = now; return; }
      if (now === this.handled) return;
      const result = await this.collect();
      this.handled = now;
      this.done(result);
    } catch {
      /* the app or the file is not ready: the next tick tries again */
    } finally {
      this.running = false;
    }
  }
}
