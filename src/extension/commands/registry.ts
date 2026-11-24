import * as vscode from "vscode";
import type { SessionLoader } from "../session/session-loader";
import type { SessionState } from "../session/session-state";

/** A group of commands that registers itself (the ids are in the manifest, `contributes.commands`). */
export interface CommandGroup {
  register(commands: CommandRegistry): vscode.Disposable[];
}

/** Registers commands. A guarded command gets the same envelope as every other: the review session exists before it runs, and a
 * failure is shown to the person as a message instead of being thrown into the editor (Template: one envelope, the body varies). */
export class CommandRegistry {
  constructor(private readonly session: SessionState, private readonly loader: SessionLoader) {}

  guarded<A extends unknown[]>(id: string, run: (...args: A) => unknown): vscode.Disposable {
    return vscode.commands.registerCommand(id, async (...args: A) => {
      try {
        if (!this.session.current) await this.loader.ensure();
        await run(...args);
      } catch (err) {
        void vscode.window.showErrorMessage(`Verdict: ${(err as Error).message}`);
      }
    });
  }
}
