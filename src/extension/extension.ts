// Verdict inside VS Code: the review of a 42 project, talking to the web app (VERDICT_API, the `web` service). It adds
//  - a Verdict view: the result and every check (a check opens the file and line it cites), and the subjects of the review;
//  - commands: open or clone a project, add subjects, run the checks, ask claude (in a VS Code terminal) or the configured AI,
//    merge claude's report into verdict.md, write a fix prompt, open verdict.md, record the result in Progress.md;
//    see what subjects the library lacks, download them from the intra, file them in the folders of their series;
//  - claude's report is merged into verdict.md by itself, each time claude saves it (report/);
//  - how files are shown: markdown as a page, JSON pretty-printed (viewers/), and the colours of .gitignore / .dockerignore files;
//  - a subject PDF opens in the editor (viewers/pdf): from the Subjects view, or from the "From x.pdf, page N" of a check.
//  - three Output channels, "Verdict: Checks", "Verdict: AI review" and "Verdict: Subjects", and the project under review in the status bar.
// Everything shown comes from untrusted input (subject PDFs, repositories): it is only ever put in labels and plain text.
//
// This file only wires: it makes the objects and hands each one what it works with (the composition root).

import * as vscode from "vscode";
import { ApiClient } from "./api/client";
import { VerdictApi } from "./api/verdict-api";
import { AiReview } from "./commands/ai-review";
import { CheckCommands } from "./commands/check-commands";
import { ClaudeReview } from "./commands/claude-review";
import { DownloadFollower } from "./commands/download-follower";
import { EnvironmentCommands } from "./commands/environment-commands";
import { ProjectCommands } from "./commands/project-commands";
import { CommandRegistry } from "./commands/registry";
import type { CommandGroup } from "./commands/registry";
import { ResultCommands } from "./commands/result-commands";
import { SubjectCommands } from "./commands/subject-commands";
import { SubjectDownloadCommands } from "./commands/subject-download-commands";
import { SubjectPlanCommands } from "./commands/subject-plan-commands";
import { SubjectReorganizeCommands } from "./commands/subject-reorganize-commands";
import { ChannelLog } from "./output/channel-log";
import type { Logs } from "./output/channel-log";
import { SessionLog } from "./output/session-log";
import { ReportFile } from "./report/report-file";
import { ReportPickup } from "./report/report-pickup";
import { ProjectFolder } from "./session/project-folder";
import { SessionLoader } from "./session/session-loader";
import { SessionPoller } from "./session/session-poller";
import { SessionState } from "./session/session-state";
import { Configuration } from "./settings/configuration";
import { readSettings } from "./settings/environment";
import { CheckNodeBuilder } from "./views/check-nodes";
import { ReviewTree } from "./views/review-tree";
import { StatusBar } from "./views/status-bar";
import { SubjectsTree } from "./views/subjects-tree";
import { DocumentViewer } from "./viewers/editor/document-viewer";
import { EditorTabs } from "./viewers/editor/editor-tabs";
import { MarkdownViewer } from "./viewers/editor/markdown-viewer";
import { VerdictViewer } from "./viewers/editor/verdict-viewer";
import { JsonViewer } from "./viewers/json/json-viewer";
import { PrettyJsonProvider } from "./viewers/json/json-provider";
import { PdfViewer } from "./viewers/pdf/pdf-viewer";

/** What most of the extension works with: the app, the session it is looking at, the project folder, the Output channels. */
interface Core {
  api: VerdictApi;
  session: SessionState;
  loader: SessionLoader;
  poller: SessionPoller;
  folder: ProjectFolder;
  logs: Logs;
}

function createCore(ctx: vscode.ExtensionContext): Core & { reportsRoot: string } {
  const settings = readSettings();
  const api = new VerdictApi(new ApiClient(settings.apiUrl));
  const session = new SessionState();
  const loader = new SessionLoader(api, session, ctx.globalState);
  return {
    api, session, loader, reportsRoot: settings.reportsRoot,
    poller: new SessionPoller(loader, session),
    folder: new ProjectFolder(settings.projectsDir, session),
    logs: {
      checks: new ChannelLog(vscode.window.createOutputChannel("Verdict: Checks")),
      ai: new ChannelLog(vscode.window.createOutputChannel("Verdict: AI review")),
      subjects: new ChannelLog(vscode.window.createOutputChannel("Verdict: Subjects")),
    },
  };
}

interface Viewers {
  documents: DocumentViewer;
  markdown: MarkdownViewer;
  json: JsonViewer;
  pdf: PdfViewer;
  verdict: VerdictViewer;
}

function createViewers(core: Core): Viewers {
  const tabs = new EditorTabs();
  const documents = new DocumentViewer();
  return {
    documents, markdown: new MarkdownViewer(tabs),
    json: new JsonViewer(new Configuration(), tabs, new PrettyJsonProvider()),
    pdf: new PdfViewer(core.session, (name, page) => core.api.pagePng(core.session.id, name, page)),
    verdict: new VerdictViewer(core.api, core.session, core.folder, tabs, documents),
  };
}

function createCommands(core: Core, viewers: Viewers): CommandGroup[] {
  const { api, session, loader, poller, folder, logs } = core;
  const project = new ProjectCommands(api, session, folder, logs);
  const subjects = new SubjectCommands(api, session, folder);
  const claude = new ClaudeReview(api, session, loader, folder, logs, viewers.verdict);
  return [project, subjects, claude,
    new CheckCommands(api, session, loader, poller, logs, project, subjects, viewers.verdict),
    new AiReview(api, session, poller, logs, claude),
    new ResultCommands(api, session, viewers.verdict, viewers.documents),
    new EnvironmentCommands(api, viewers.documents),
    new SubjectPlanCommands(api, logs.subjects),
    new SubjectDownloadCommands(api, new DownloadFollower(api, logs.subjects), logs.subjects),
    new SubjectReorganizeCommands(api, logs.subjects)];
}

export function activate(ctx: vscode.ExtensionContext): void {
  const core = createCore(ctx);
  const viewers = createViewers(core);
  const { session, logs } = core;
  const status = new StatusBar(vscode.window.createStatusBarItem("verdict.project", vscode.StatusBarAlignment.Left, 100), session);
  const sessionLog = new SessionLog(session, logs);
  const pickup = new ReportPickup(core.api, session, core.loader, new ReportFile(core.reportsRoot), logs, viewers.verdict);
  const registry = new CommandRegistry(session, core.loader);

  ctx.subscriptions.push(
    ...createCommands(core, viewers).flatMap((group) => group.register(registry)),
    ...viewers.documents.register(), ...viewers.markdown.register(), ...viewers.json.register(), ...viewers.pdf.register(),
    vscode.window.registerTreeDataProvider("verdict.review", new ReviewTree(session, new CheckNodeBuilder(core.folder))),
    vscode.window.registerTreeDataProvider("verdict.subjects", new SubjectsTree(session)),
    session.onDidChange(() => { viewers.pdf.sync(); sessionLog.track(); status.refresh(); }),
    status, logs.checks, logs.ai, logs.subjects, session, core.poller, pickup);
  pickup.start();
  status.refresh();
  core.loader.ensure().then(() => { if (session.busy()) core.poller.start(); }, (err: Error) => {
    status.unavailable(err.message);
    logs.checks.line(err.message);
  });
}
