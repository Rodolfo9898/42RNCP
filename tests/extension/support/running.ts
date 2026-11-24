import * as fs from "node:fs";
import * as path from "node:path";
import { mock } from "node:test";
import type * as vscode from "vscode";
import { editor } from "./vscode-module";
import { activate } from "../../../src/extension/extension";
import type { SessionView } from "../../../src/extension/api/types";
import { FakeApp } from "./fake-app";
import { aMerge, aSession } from "./fixtures";
import { pause, scratch } from "./harness";

/** A web app that cannot be reached: every `fetch` fails the way a refused connection does. */
function unreachable(): () => void {
  const real = globalThis.fetch;
  globalThis.fetch = (async () => { throw new Error("connect ECONNREFUSED"); }) as typeof fetch;
  return () => { globalThis.fetch = real; };
}

/** The whole extension running (the composition root, `activate`) against a fake web app and a fake editor, with the timers under the
 * test's control: `ticks(n)` lets n report-watch ticks (2 seconds each) go by. `reachable = false`: the app is down. */
export interface Running {
  app: FakeApp;
  session: SessionView;
  projects: string;
  reports: string;
  report: string;
  ctx: vscode.ExtensionContext;
  ticks(n: number): Promise<void>;
  stop(): void;
}

export async function running(extra: Partial<SessionView> = {}, reachable = true): Promise<Running> {
  const projects = scratch();
  const reports = scratch();
  fs.mkdirSync(path.join(projects, "cub3d"));
  fs.writeFileSync(path.join(projects, "cub3d", "verdict.md"), "# verdict\n");
  fs.mkdirSync(path.join(reports, "s1"));
  process.env.PROJECTS_DIR = projects;
  process.env.REPORTS_ROOT = reports;
  editor.reset();
  const session = aSession(extra);
  const app = new FakeApp()
    .on("GET sessions/s1", () => session)
    .on("GET health", { llm: { provider: "claude-cli", configured: true, model: "", host: "" } })
    .on("GET sessions/s1/prompts/review", { text: "review this project" })
    .on("PUT sessions/s1/claude-review", aMerge());
  const restoreFetch = reachable ? app.install() : unreachable();
  mock.timers.enable({ apis: ["setInterval"] });
  const ctx = { subscriptions: [], globalState: { get: () => "s1", update: async () => {} } } as unknown as vscode.ExtensionContext;
  activate(ctx);
  await pause(30);                                                       // (the session is fetched)
  return {
    app, session, projects, reports, ctx, report: path.join(reports, "s1", "claude-review.md"),
    ticks: async (n) => { for (let i = 0; i < n; i++) { mock.timers.tick(2000); await pause(30); } },
    stop: () => { ctx.subscriptions.forEach((s) => s.dispose()); mock.timers.reset(); restoreFetch(); },
  };
}
