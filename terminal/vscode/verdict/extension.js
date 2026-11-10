"use strict";

// Verdict inside VS Code: the review of a 42 project, talking to the web app (VERDICT_API, the `web` service). It adds
//  - a Verdict view: the result and every check (a check opens the file and line it cites), and the subjects of the review;
//  - commands: open or clone a project, add subjects, run the checks, ask claude (in a VS Code terminal) or the configured AI,
//    merge claude's report into verdict.md, write a fix prompt, open verdict.md;
//  - claude's report is merged into verdict.md by itself, each time claude saves it (report.js);
//  - how files are shown: markdown as a page, JSON pretty-printed (viewers.js), and the colours of .gitignore / .dockerignore files.
//  - two Output channels, "Verdict: Checks" and "Verdict: AI review", and the project under review in the status bar.
// Everything shown comes from untrusted input (subject PDFs, repositories): it is only ever put in labels and plain text.

const vscode = require("vscode");
const fs = require("fs");
const os = require("os");
const path = require("path");
const reports = require("./report");
const viewers = require("./viewers");

const API = (process.env.VERDICT_API || "http://web:8000").replace(/\/$/, "");
const PROJECTS = process.env.PROJECTS_DIR || "/projects";
const REPORTS = (process.env.REPORTS_ROOT || "/scratch/reports").replace(/\/$/, "");     // where claude saves its report: <here>/<session>/claude-review.md
const REPORT_TICK = 2000;
const ORDER = ["fail", "warn", "manual", "skipped", "na", "pass"];
const TITLES = { fail: "Failed", warn: "Warnings", manual: "Needs manual review", skipped: "Not checked", na: "Not applicable", pass: "Passed" };
const ICONS = { fail: ["error", "errorForeground"], warn: ["warning", "editorWarning.foreground"], manual: ["question", "editorInfo.foreground"],
  skipped: ["dash", undefined], na: ["circle-slash", undefined], pass: ["pass", "testing.iconPassed"] };
const REVIEWED_STATUS = { likely_problem: "fail", unclear: "manual", likely_ok: "pass", not_applicable: "pass" };

let session = null;
let sid = null;
let llm = { provider: "", configured: false };
let polling = null;
let context = null;
const changed = new vscode.EventEmitter();
const checksLog = vscode.window.createOutputChannel("Verdict: Checks");
const aiLog = vscode.window.createOutputChannel("Verdict: AI review");

// ------------------------------------------------------------------ the web app

async function api(route, { method = "GET", body, form } = {}) {
  const init = { method, headers: {} };
  if (form) init.body = form;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers["content-type"] = "application/json"; }
  let response;
  try {
    response = await fetch(`${API}/api/${route}`, init);
  } catch (err) {
    throw new Error(`the Verdict service (${API}) cannot be reached: ${err.message}`);
  }
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!response.ok) {
    const detail = data && typeof data === "object" ? data.detail : data;
    const error = new Error(typeof detail === "string" ? detail : `${response.status} ${response.statusText}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function ensureSession() {
  sid = context.globalState.get("verdict.session") || null;
  if (sid) {
    try { return setSession(await api(`sessions/${sid}`)); } catch (err) { if (err.status !== 404) throw err; }
  }
  const fresh = await api("sessions", { method: "POST" });
  sid = fresh.id;
  await context.globalState.update("verdict.session", sid);
  return setSession(fresh);
}

function setSession(data) {
  session = data;
  trackOutput();
  changed.fire();
  status.refresh();
  return session;
}

const busy = () => !!session && (["running", "cloning"].includes(session.state) || session.ai?.state === "running");

function poll() {
  if (polling) return;
  polling = setInterval(async () => {
    try { setSession(await api(`sessions/${sid}`)); } catch { /* the next tick tries again */ }
    if (!busy()) { clearInterval(polling); polling = null; finished(); }
  }, 1000);
}

// After a run: the new verdict.md is opened.
let wasRunning = false;
function finished() {
  if (wasRunning && session?.results?.length) openVerdict(true).catch(() => {});
  wasRunning = false;
}

// ------------------------------------------------------------------ the Output channels

const seen = { state: null, message: null, aiSteps: 0, aiState: null };
const stamp = () => new Date().toTimeString().slice(0, 8);
const logTo = (channel, text) => { if (text) channel.appendLine(`[${stamp()}] ${text}`); };

function trackOutput() {
  if (!session) return;
  if (session.state !== seen.state) {
    logTo(checksLog, { idle: "Ready.", cloning: "Cloning the repository…", running: "Running the checks…", done: "The checks are done.",
      error: `The run failed: ${session.message}` }[session.state] ?? session.state);
    seen.state = session.state;
  }
  if (session.message && session.message !== seen.message) { logTo(checksLog, session.message); seen.message = session.message; }
  const steps = session.ai?.progress ?? [];
  if (steps.length < seen.aiSteps) seen.aiSteps = 0;
  for (const step of steps.slice(seen.aiSteps)) logTo(aiLog, step.text);
  seen.aiSteps = steps.length;
  const ai = session.ai?.state;
  if (ai !== seen.aiState) {
    if (seen.aiState !== null && ai !== "idle") logTo(aiLog, `AI review: ${ai}${session.ai.message ? ` (${session.ai.message})` : ""}`);
    seen.aiState = ai;
  }
}

// ------------------------------------------------------------------ the status bar: the project under review

const status = {
  item: vscode.window.createStatusBarItem("verdict.project", vscode.StatusBarAlignment.Left, 100),
  refresh() {
    const repo = session?.repo;
    const result = session?.results?.length ? ` · ${session.summary.overall}` : "";
    const state = busy() ? "$(sync~spin) " : "$(shield) ";
    this.item.name = "Verdict: project";
    this.item.text = repo ? `${state}${repo.name || repo.path}${repo.commit ? ` @ ${repo.commit}` : ""}${result}` : `${state}no project`;
    this.item.tooltip = repo ? `Under review: ${repo.path}${repo.url ? ` (${repo.url})` : ""}. Click to review another project.` : "Pick the project to review";
    this.item.command = "verdict.openProject";
    this.item.show();
  },
};

// ------------------------------------------------------------------ the views

function shownStatus(r) {
  const review = r.status === "manual" && r.rule_id && session.ai?.reviews ? session.ai.reviews[r.rule_id] : null;
  return review ? (REVIEWED_STATUS[review.assessment] ?? "manual") : r.status;
}

function themed(status) {
  const [id, color] = ICONS[status] || ["circle-outline", undefined];
  return new vscode.ThemeIcon(id, color ? new vscode.ThemeColor(color) : undefined);
}

function projectDir() {
  return session?.repo?.path ? path.join(PROJECTS, session.repo.path) : null;
}

function fileUri(file) {
  const root = projectDir();
  if (!root) return null;
  const full = path.resolve(root, file);
  return full === root || full.startsWith(root + path.sep) ? vscode.Uri.file(full) : null;     // never outside the project
}

class ReviewTree {
  constructor() { this.onDidChangeTreeData = changed.event; }

  getTreeItem(node) { return node.item; }

  getChildren(node) {
    if (!session || !session.repo) return [];
    if (!node) return this.top();
    return node.children ? node.children() : [];
  }

  top() {
    const nodes = [];
    const s = session.summary || {};
    const result = new vscode.TreeItem(session.results.length ? `Result: ${s.overall}` : (busy() ? "Running…" : "Not run yet"));
    result.description = session.results.length ? (s.decided_by === "claude" ? "decided by claude" : "from the checks") : "Run the checks";
    result.tooltip = s.reason || (session.results.length ? "FAIL when anything is lacking, PASS WITH ISSUES when something needs a second look, PASS otherwise." : "");
    result.iconPath = new vscode.ThemeIcon(busy() ? "sync~spin" : "shield");
    if (!session.results.length && !busy()) result.command = { command: "verdict.runChecks", title: "Run Checks" };
    nodes.push({ item: result });
    if (session.ai?.state && session.ai.state !== "idle") {
      const ai = new vscode.TreeItem(`AI review: ${session.ai.state}`);
      ai.description = session.ai.message || "";
      ai.iconPath = new vscode.ThemeIcon(session.ai.state === "running" ? "sync~spin" : "sparkle");
      ai.command = { command: "verdict.showAiLog", title: "Show the AI's log" };
      nodes.push({ item: ai });
    }
    for (const st of ORDER) {
      const items = session.results.filter((r) => shownStatus(r) === st);
      if (!items.length) continue;
      const group = new vscode.TreeItem(`${TITLES[st]} (${items.length})`,
        st === "pass" || st === "na" ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.Expanded);
      group.iconPath = themed(st);
      nodes.push({ item: group, children: () => items.map((r) => this.check(r)) });
    }
    return nodes;
  }

  check(r) {
    const evidence = r.evidence || [];
    const extra = [];
    const review = r.rule_id && session.ai?.reviews ? session.ai.reviews[r.rule_id] : null;
    if (review) {
      const it = new vscode.TreeItem(`${review.by || "AI"}: ${review.assessment.replace(/_/g, " ")}`);
      it.description = review.finding || "";
      it.tooltip = [review.finding, review.why_manual && `Check by hand: ${review.why_manual}`, "AI-generated, unverified"].filter(Boolean).join("\n\n");
      it.iconPath = new vscode.ThemeIcon("sparkle");
      extra.push({ item: it });
    }
    for (const e of evidence) {
      const uri = fileUri(e.file);
      const it = new vscode.TreeItem(e.line ? `${e.file}:${e.line}` : e.file);
      it.description = e.snippet || "";
      it.iconPath = new vscode.ThemeIcon("go-to-file");
      if (uri) {
        const line = Math.max((e.line || 1) - 1, 0);
        it.command = { command: "vscode.open", title: "Open", arguments: [uri, { selection: new vscode.Range(line, 0, line, 0) }] };
      }
      extra.push({ item: it });
    }
    if (r.log) {
      const it = new vscode.TreeItem("Show the log");
      it.iconPath = new vscode.ThemeIcon("output");
      it.command = { command: "verdict.showText", title: "Show the log", arguments: [r.log, "log"] };
      extra.push({ item: it });
    }
    for (const src of (r.sources || []).slice(0, 4)) {
      const it = new vscode.TreeItem(`From ${src.pdf}${src.page ? `, page ${src.page}` : ""}`);
      it.iconPath = new vscode.ThemeIcon("file-pdf");
      extra.push({ item: it });
    }
    const item = new vscode.TreeItem(`${r.title}${r.section === "bonus" ? " [bonus]" : ""}`,
      extra.length ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None);
    item.description = r.detail || "";
    item.tooltip = new vscode.MarkdownString();
    item.tooltip.appendText(`${r.title}\n\n${r.detail || ""}${r.by === "Claude" ? "\n\n(from claude's review)" : ""}`);
    item.iconPath = themed(shownStatus(r));
    if (extra.length === 1 && extra[0].item.command) item.command = extra[0].item.command;
    return { item, children: () => extra };
  }
}

class SubjectsTree {
  constructor() { this.onDidChangeTreeData = changed.event; }

  getTreeItem(node) { return node; }

  getChildren(node) {
    if (node || !session) return [];
    return session.subjects.map((s) => {
      const item = new vscode.TreeItem(s.name);
      item.description = s.kind === "norm" ? "the Norm (C code was found)" : [s.track, `${s.rules.length} rules`, s.lang && s.lang.toUpperCase()].filter(Boolean).join(" · ");
      item.tooltip = s.rules.map((r) => `${r.kind === "manual" ? "?" : "⚙"} ${r.title}`).join("\n");
      item.iconPath = new vscode.ThemeIcon(s.kind === "norm" ? "law" : "file-pdf");
      item.contextValue = s.kind === "norm" ? "norm" : "subject";
      item.subject = s.name;
      return item;
    });
  }
}

// ------------------------------------------------------------------ the commands

function guarded(fn) {
  return async (...args) => {
    try {
      if (!session) await ensureSession();
      await fn(...args);
    } catch (err) {
      vscode.window.showErrorMessage(`Verdict: ${err.message}`);
    }
  };
}

async function openProject() {
  const { folders } = await api("projects/existing");
  if (!folders.length) {
    const pick = await vscode.window.showInformationMessage(`There is no project in ${PROJECTS} yet.`, "Clone a Repository…");
    if (pick) await cloneProject();
    return;
  }
  const items = folders.map((f) => ({ label: f.path, description: f.git ? "" : "not a git repository" }));
  const active = vscode.window.activeTextEditor?.document.uri.fsPath;
  const here = active ? items.filter((i) => active.startsWith(path.join(PROJECTS, i.label) + path.sep)).sort((x, y) => y.label.length - x.label.length)[0] : null;
  if (here) {
    items.splice(items.indexOf(here), 1);
    items.unshift({ ...here, description: ["the open file's project", here.description].filter(Boolean).join(" · ") });
  }
  const choice = await vscode.window.showQuickPick(items, { title: "Review which project?", placeHolder: "A folder of the projects folder", matchOnDescription: true });
  if (!choice) return;
  setSession(await api(`sessions/${sid}/repo/existing`, { method: "POST", body: { path: choice.label } }));
  logTo(checksLog, `Project: ${session.repo.path} @ ${session.repo.commit}`);
  await revealProject();
}

async function cloneProject() {
  const url = await vscode.window.showInputBox({ title: "Clone a repository", prompt: "Its git URL (SSH, e.g. git@vogsphere…, or HTTPS)", ignoreFocusOut: true });
  if (!url) return;
  const { folders } = await api("projects");
  const destination = folders && folders.length
    ? await vscode.window.showQuickPick(["(the projects folder itself)", ...folders.map((f) => (typeof f === "string" ? f : f.path))], { title: "Clone it into which folder?" })
    : "(the projects folder itself)";
  if (destination === undefined) return;
  const name = await vscode.window.showInputBox({ title: "Name of the folder", prompt: "Empty: the repository's name", ignoreFocusOut: true });
  if (name === undefined) return;
  await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: `Cloning ${url}…` }, async () => {
    setSession(await api(`sessions/${sid}/repo`, { method: "POST",
      body: { url, name, destination: destination.startsWith("(") ? "" : destination } }));
  });
  logTo(checksLog, `Project: ${session.repo.path} @ ${session.repo.commit}`);
  await revealProject();
}

async function revealProject() {
  const dir = projectDir();
  if (dir) await vscode.commands.executeCommand("revealInExplorer", vscode.Uri.file(dir)).then(undefined, () => {});
}

async function addSubjects() {
  const lib = await api("library");
  if (!lib.items.length) return vscode.window.showInformationMessage(`The library is empty: put PDFs in ${lib.tracks.map((t) => `samples/${t.id}/`).join(", ")}, or upload one.`);
  const have = new Set(session.subjects.map((s) => s.name));
  const label = Object.fromEntries(lib.tracks.map((t) => [t.id, t.label]));
  const project = (session.repo?.name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const matches = (name) => !!project && name.replace(/\.pdf$/i, "").toLowerCase().replace(/[^a-z0-9]/g, "") === project;
  const items = [];
  for (const t of lib.tracks) {
    const inTrack = lib.items.filter((i) => i.track === t.id);
    if (!inTrack.length) continue;
    items.push({ label: label[t.id], kind: vscode.QuickPickItemKind.Separator });
    for (const i of inTrack)                                    // the project's own subject comes ticked: Enter adds it
      items.push({ label: i.name, description: have.has(i.name) ? "in this review" : matches(i.name) ? "this project's subject" : "",
        picked: have.has(i.name) || matches(i.name), path: i.path });
  }
  const picks = await vscode.window.showQuickPick(items, { canPickMany: true, title: "Add subjects", placeHolder: project ? `e.g. ${session.repo.name}.pdf` : "Pick the subject PDFs", matchOnDescription: true });
  if (!picks) return;
  const paths = picks.filter((p) => p.path && !have.has(p.label)).map((p) => p.path);
  if (paths.length) setSession(await api(`sessions/${sid}/subjects/library`, { method: "POST", body: { paths } }));
}

async function uploadSubject() {
  const files = await vscode.window.showOpenDialog({ canSelectMany: true, filters: { "Subject PDF": ["pdf"] }, title: "Upload subject PDFs",
    defaultUri: vscode.Uri.file(projectDir() || PROJECTS) });
  if (!files || !files.length) return;
  const lib = await api("library");
  const track = await vscode.window.showQuickPick(lib.tracks.map((t) => ({ label: t.label, description: `samples/${t.id}/`, id: t.id })),
    { title: "Where does this subject belong?", placeHolder: "It is added to this review and kept in that library folder" });
  if (!track) return;
  const form = new FormData();
  form.append("track", track.id);
  for (const f of files) form.append("files", new Blob([await vscode.workspace.fs.readFile(f)], { type: "application/pdf" }), path.basename(f.fsPath));
  setSession(await api(`sessions/${sid}/subjects`, { method: "POST", form }));
}

async function removeSubject(item) {
  const name = item?.subject;
  if (name) setSession(await api(`sessions/${sid}/subjects/${encodeURIComponent(name)}`, { method: "DELETE" }));
}

async function runChecks() {
  if (!session.repo) { await openProject(); if (!session.repo) return; }
  if (!session.subjects.some((s) => s.kind === "subject")) { await addSubjects(); if (!session.subjects.some((s) => s.kind === "subject")) return; }
  await vscode.workspace.saveAll(false);
  logTo(checksLog, "— a new run starts from nothing —");
  setSession(await api(`sessions/${sid}/run`, { method: "POST" }));
  wasRunning = true;
  checksLog.show(true);
  poll();
}

async function aiReview() {
  if (!session.results?.length) return vscode.window.showWarningMessage("Run the checks first: the AI is asked about what they could not judge.");
  llm = (await api("health")).llm || llm;
  if (llm.provider === "claude-cli") return claudeReview();
  if (!llm.configured) return vscode.window.showWarningMessage("No AI is configured: set ANTHROPIC_API_KEY, or LLM_BASE_URL + LLM_API_KEY + LLM_MODEL, in .env.");
  const go = await vscode.window.showWarningMessage(`Send the source files of ${session.repo.path} to ${llm.host} (${llm.model})?`,
    { modal: true, detail: "The student's code leaves this computer. Its answers count in the result." }, "Send and review");
  if (!go) return;
  setSession(await api(`sessions/${sid}/ai`, { method: "POST" }));
  aiLog.show(true);
  poll();
}

// claude in a VS Code terminal, in the project folder, started with the review prompt; it saves its report outside the project.
async function claudeReview() {
  const go = await vscode.window.showInformationMessage("Ask claude to review what the checks could not?", { modal: true,
    detail: `claude gets a prompt built from this run: what the scripts verified, and everything they could not judge. It works in ${session.repo.path} itself, asks before running anything, and its decision sets the result once you merge its report.` }, "Run");
  if (!go) return;
  const { text } = await api(`sessions/${sid}/review-prompt`);
  const file = path.join(os.tmpdir(), `verdict-prompt-${sid}-${Date.now()}.txt`);
  fs.writeFileSync(file, text, { mode: 0o600 });
  const terminal = vscode.window.createTerminal({ name: "claude: review", cwd: projectDir(), iconPath: new vscode.ThemeIcon("sparkle"),
    shellPath: "python3", shellArgs: ["-m", "verdict.editor", "claude", "--session", sid, "--project", projectDir(), "--prompt-file", file] });
  terminal.show();
  logTo(aiLog, `claude started in the terminal "claude: review" with the review prompt (${text.length} characters).`);
  vscode.window.showInformationMessage("claude's report goes into verdict.md by itself, each time it saves it.");
}

// What a merge did, in words.
function describeMerge(r) {
  const file = r.verdict_file || "verdict.md";
  if (!r.structured) return `claude's report was added to ${file} as text: it has no data block at the end, so it could not be merged into the lists. ${(r.problems || [])[0] || ""}`.trim();
  return `Merged claude's answers (${r.assessed} of ${r.total} requirements) into ${file}.${r.assessed < r.total ? ` ${r.total - r.assessed} requirement(s) were not answered.` : ""}`;
}

async function mergeClaudeReview() {
  const r = await api(`sessions/${sid}/claude-review/save`, { method: "POST" });
  setSession(await api(`sessions/${sid}`));
  if (r.warning) vscode.window.showWarningMessage(r.warning);
  const message = describeMerge(r);
  logTo(aiLog, message);
  vscode.window.showInformationMessage(message);
  await openVerdict(false);
}

// claude saved its report (again): the app has merged it into verdict.md. Show what changed, without taking the focus from the
// terminal claude is typing in.
async function reportMerged(r) {
  try {
    if (r.stale) {
      logTo(aiLog, "claude's report is for an earlier run of the checks or another project, so it is not merged: ask claude again (AI Review).");
      return;
    }
    if (!r.new && !r.written) return;
    setSession(await api(`sessions/${sid}`));
    if (!r.new) return;
    const message = describeMerge(r);
    logTo(aiLog, message);
    vscode.window.showInformationMessage(message);
    await openVerdict(true);
  } catch (err) {
    logTo(aiLog, `claude's report was merged, but the view could not be refreshed: ${err.message}`);
  }
}

// Looks at claude's report every couple of seconds (a stat of one file) and has it merged each time it is saved.
function watchReport(ctx) {
  const watch = reports.watcher({
    look: () => (sid ? reports.signature(fs.promises.stat, path.join(REPORTS, sid, reports.REPORT_NAME)) : Promise.resolve(null)),
    collect: () => api(`sessions/${sid}/claude-review/collect`, { method: "POST" }),
    done: reportMerged,
  });
  const timer = setInterval(() => watch.tick(), REPORT_TICK);
  ctx.subscriptions.push({ dispose: () => clearInterval(timer) });
}

async function fixPrompt() {
  const r = await api(`sessions/${sid}/fix-prompt`);
  if (!r.text) return vscode.window.showInformationMessage("Nothing to fix: the review found nothing lacking.");
  await showText(r.text, "markdown");
  vscode.window.showInformationMessage(`${r.must_fix} to fix, ${r.look_at} to look at. Paste it into claude in the project's folder (you can edit it first).`, "Copy")
    .then((copy) => copy && vscode.env.clipboard.writeText(r.text));
}

// verdict.md as a page (markdown opens as the page; the button in its title bar shows the code). `quiet`: it opens without taking the
// focus, and an editor that has it already is left as it is (VS Code reloads it when the file changes).
async function openVerdict(quiet) {
  if (!session.results?.length) return vscode.window.showInformationMessage("Run the checks first.");
  const file = session.verdict_file && fileUri(session.verdict_file);
  if (file && fs.existsSync(file.fsPath)) {
    if (quiet && viewers.isOpen(file.fsPath)) return;
    await vscode.commands.executeCommand("vscode.open", file, { preview: false, preserveFocus: !!quiet });
    return;
  }
  const text = await (await fetch(`${API}/api/sessions/${sid}/verdict.md`)).text();
  await showMarkdown(text);
}

async function showText(content, language, beside) {
  const doc = await vscode.workspace.openTextDocument({ content, language });
  await vscode.window.showTextDocument(doc, { preview: false, viewColumn: beside ? vscode.ViewColumn.Beside : undefined });
}

// Markdown that is not a file (a report made on the spot): shown as the page, with its code one click away in the Markdown preview.
async function showMarkdown(content) {
  const doc = await vscode.workspace.openTextDocument({ content, language: "markdown" });
  await vscode.window.showTextDocument(doc, { preview: false });
  await vscode.commands.executeCommand("markdown.showPreview", doc.uri).then(undefined, () => {});
}

async function checkEnvironment() {
  const deep = await vscode.window.showQuickPick([
    { label: "Quick", description: "tool versions, C and C++ through make, the Docker daemon", deep: false },
    { label: "Full", description: "also builds and runs a tiny Dockerfile (downloads a base image: needs internet)", deep: true }],
    { title: "Check the Environment", placeHolder: "Where the checks run (sandbox) and where claude works (terminal)" });
  if (!deep) return;
  const env = await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "Checking the environment…" },
    () => api(`environment${deep.deep ? "?deep=true" : ""}`));
  const lines = [`# The environment: ${env.ready ? "ready" : "NOT ready"}`, ""];
  for (const [key, title] of [["sandbox", "Sandbox (runs the checks, no network)"], ["terminal", "Terminal (this editor, claude)"]]) {
    const part = env[key] || {};
    lines.push(`## ${title}`, "");
    if (!part.available) lines.push(`✖ ${part.error || "not available"}`, "");
    for (const tool of part.tools || []) lines.push(`- ${tool.ok ? "✔" : tool.required ? "✖" : "⚠"} **${tool.name}**: ${String(tool.detail || "").replace(/\s+/g, " ")}`);
    lines.push("");
  }
  lines.push("Only ✖ makes it not ready.");
  await showMarkdown(lines.join("\n"));
}

async function refresh() {
  setSession(await api(`sessions/${sid}`));
  if (busy()) poll();
}

// ------------------------------------------------------------------ start

function activate(ctx) {
  context = ctx;
  const command = (id, fn) => ctx.subscriptions.push(vscode.commands.registerCommand(id, guarded(fn)));
  command("verdict.openProject", openProject);
  command("verdict.cloneProject", cloneProject);
  command("verdict.addSubjects", addSubjects);
  command("verdict.uploadSubject", uploadSubject);
  command("verdict.removeSubject", removeSubject);
  command("verdict.runChecks", runChecks);
  command("verdict.aiReview", aiReview);
  command("verdict.mergeClaudeReview", mergeClaudeReview);
  command("verdict.fixPrompt", fixPrompt);
  command("verdict.openVerdict", () => openVerdict(false));
  command("verdict.refresh", refresh);
  command("verdict.checkEnvironment", checkEnvironment);
  ctx.subscriptions.push(vscode.commands.registerCommand("verdict.showText", (text, language) => showText(text, language)));
  ctx.subscriptions.push(vscode.commands.registerCommand("verdict.showAiLog", () => aiLog.show()));
  ctx.subscriptions.push(vscode.window.registerTreeDataProvider("verdict.review", new ReviewTree()));
  ctx.subscriptions.push(vscode.window.registerTreeDataProvider("verdict.subjects", new SubjectsTree()));
  ctx.subscriptions.push(status.item, checksLog, aiLog, changed);
  viewers.activate(ctx);
  watchReport(ctx);
  status.refresh();
  ensureSession().then(() => { if (busy()) poll(); }, (err) => {
    status.item.text = "$(warning) Verdict unavailable";
    status.item.tooltip = err.message;
    logTo(checksLog, err.message);
  });
}

function deactivate() {
  if (polling) clearInterval(polling);
}

module.exports = { activate, deactivate };
