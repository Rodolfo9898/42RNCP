import type { SessionView } from "../api/types";
import type { SessionState } from "../session/session-state";
import type { Logs } from "./channel-log";

const STATE_TEXT: Record<string, (view: SessionView) => string> = {
  idle: () => "Ready.",
  cloning: () => "Cloning the repository…",
  running: () => "Running the checks…",
  done: () => "The checks are done.",
  error: (view) => `The run failed: ${view.message}`,
};

/** Writes into the Output channels what changed in the session since the last change it saw (Observer of the session state). */
export class SessionLog {
  private state: string | null = null;
  private message: string | null = null;
  private aiSteps = 0;
  private aiState: string | null = null;

  constructor(private readonly session: SessionState, private readonly logs: Logs) {}

  track(): void {
    const view = this.session.current;
    if (!view) return;
    this.checks(view);
    this.ai(view);
  }

  private checks(view: SessionView): void {
    if (view.state !== this.state) {
      this.logs.checks.line(STATE_TEXT[view.state]?.(view) ?? view.state);
      this.state = view.state;
    }
    if (view.message && view.message !== this.message) {
      this.logs.checks.line(view.message);
      this.message = view.message;
    }
  }

  private ai(view: SessionView): void {
    const steps = view.ai.progress ?? [];
    if (steps.length < this.aiSteps) this.aiSteps = 0;
    for (const step of steps.slice(this.aiSteps)) this.logs.ai.line(step.text);
    this.aiSteps = steps.length;
    const state = view.ai.state;
    if (state !== this.aiState) {
      if (this.aiState !== null && state !== "idle") this.logs.ai.line(`AI review: ${state}${view.ai.message ? ` (${view.ai.message})` : ""}`);
      this.aiState = state;
    }
  }
}
