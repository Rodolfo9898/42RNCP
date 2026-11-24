import * as vscode from "vscode";
import type { SessionView } from "../api/types";

/** The review session the editor is looking at (State holder): the last view the app sent, and a change event for everything that
 * shows it (Observer: the views, the status bar, the Output channels, the PDF tabs). */
export class SessionState implements vscode.Disposable {
  private view: SessionView | null = null;
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChange: vscode.Event<void> = this.emitter.event;

  get current(): SessionView | null { return this.view; }

  /** The session, for what only runs once there is one (every command is guarded: the session is restored before it runs). */
  require(): SessionView {
    if (!this.view) throw new Error("the review session is not loaded yet");
    return this.view;
  }

  get id(): string { return this.require().id; }

  /** Is the app working on this session (cloning, running the checks, the AI review)? */
  busy(): boolean {
    const view = this.view;
    return !!view && (["running", "cloning"].includes(view.state) || view.ai.state === "running");
  }

  set(view: SessionView): SessionView {
    this.view = view;
    this.emitter.fire();
    return view;
  }

  dispose(): void { this.emitter.dispose(); }
}
