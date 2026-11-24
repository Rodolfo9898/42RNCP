import type * as vscode from "vscode";
import type { SessionState } from "../session/session-state";

/** The project under review, in the status bar (a click picks another one). */
export class StatusBar implements vscode.Disposable {
  constructor(private readonly item: vscode.StatusBarItem, private readonly session: SessionState) {}

  refresh(): void {
    const view = this.session.current;
    const repo = view?.repo;
    const result = view?.results.length ? ` · ${view.summary.overall}` : "";
    const state = this.session.busy() ? "$(sync~spin) " : "$(shield) ";
    this.item.name = "Verdict: project";
    this.item.text = repo ? `${state}${repo.name || repo.path}${repo.commit ? ` @ ${repo.commit}` : ""}${result}` : `${state}no project`;
    this.item.tooltip = repo ? `Under review: ${repo.path}${repo.url ? ` (${repo.url})` : ""}. Click to review another project.` : "Pick the project to review";
    this.item.command = "verdict.openProject";
    this.item.show();
  }

  /** The app cannot be reached: say so where it is seen. */
  unavailable(reason: string): void {
    this.item.text = "$(warning) Verdict unavailable";
    this.item.tooltip = reason;
  }

  dispose(): void { this.item.dispose(); }
}
