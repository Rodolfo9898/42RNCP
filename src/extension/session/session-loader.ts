import * as vscode from "vscode";
import { ApiError } from "../api/client";
import type { VerdictApi } from "../api/verdict-api";
import type { SessionView } from "../api/types";
import type { SessionState } from "./session-state";

const REMEMBERED = "verdict.session";

/** Gets the session into the state: the one the editor had (it is remembered across restarts), a new one when the app does not
 * know it any more, and a fresh read of it on demand. */
export class SessionLoader {
  constructor(private readonly api: VerdictApi, private readonly session: SessionState, private readonly memory: vscode.Memento) {}

  async ensure(): Promise<SessionView> {
    const remembered = this.memory.get<string>(REMEMBERED);
    if (remembered) {
      try {
        return this.session.set(await this.api.session(remembered));
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 404) throw err;
      }
    }
    const fresh = await this.api.createSession();
    await this.memory.update(REMEMBERED, fresh.id);
    return this.session.set(fresh);
  }

  refresh(): Promise<SessionView> {
    return this.api.session(this.session.id).then((view) => this.session.set(view));
  }
}
