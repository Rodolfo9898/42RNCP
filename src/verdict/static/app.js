"use strict";

// The review itself: the session on the server, the Verdict tab, the lists of the panel, the dialogs (open a project, upload, library,
// environment, AI review, fix prompt) and the run. The workbench around it (layout, editors, terminals, menus, keys, status bar) is in the
// other files. Everything shown comes from untrusted input (PDFs, repositories): build DOM with textContent only, never innerHTML.
// Shared helpers (h, markdown, rainbow brackets) are in lib.js; the small things everything stands on (api, toast, dialog) in core.js.

const ICON = { fail: "✖", warn: "!", manual: "?", skipped: "–", na: "∅", pass: "✔" };
const ORDER = ["fail", "warn", "manual", "skipped", "na", "pass"];
const SHORT = { fail: "Failed", warn: "Warnings", manual: "Manual", skipped: "Skipped", na: "N/A", pass: "Passed" };
const TITLES = { fail: "Failed", warn: "Warnings", manual: "Needs manual review", skipped: "Not checked", na: "Not applicable", pass: "Passed" };

let sid = null;
let session = null;
let sandboxUp = false;
let llm = { configured: false, model: "" };
let ssh = null;
const shown = new Set(ORDER);
let polling = false;

// ------------------------------------------------------------------ session

async function init() {
  applyTheme();
  applyEditorSettings();
  loadBindings();
  buildTitleBar();
  try { sid = new URLSearchParams(location.search).get("session") || localStorage.getItem("verdict.session"); } catch { sid = null; }
  if (sid) {
    try { session = await api(`sessions/${sid}`); } catch { sid = null; }
  }
  if (!sid) {
    session = await post("sessions");
    sid = session.id;
    try { localStorage.setItem("verdict.session", sid); } catch { /* storage unavailable: a new session after a reload */ }
  }
  const health = await api("health").catch(() => ({}));
  sandboxUp = health.sandbox === true;
  llm = health.llm || llm;
  await loadIconTheme();   // before the first render, so the explorer has its icons from the start
  addTab("overview", "Verdict", h("div", { class: "view overview" }), false);
  Object.assign(tabs.get("overview"), { kind: "overview", iconEl: () => icon("verdict", 14) });
  showTab("overview");
  initLayout();            // the activity bar, the side bars, the panel and the views in them (they read the session)
  buildStatusBar();
  render();
  refreshSsh();            // (after the Verdict tab exists: it renders into it)
  loadTree();              // (the files are needed by Go to File even when the explorer is not on show)
  await restoreTabs();     // the files that were open before a reload
  if (session.state === "running" || session.ai.state === "running") poll();
  else if (session.results.length) refreshVerdict(false).catch(() => {});
}

async function refreshSsh() {
  ssh = await api("ssh").catch(() => null);
  render();
}

function setSession(next) {
  session = next;
  render();
}

function busy() { return session.state === "running" || session.state === "cloning" || session.ai.state === "running"; }

// ------------------------------------------------------------------ rendering

// New data from the server: every part of the page that shows it draws itself again. The page asks every second while a run goes on, and
// most of the time nothing changed: then nothing is drawn (a selection, a scroll or a click in the middle of it would be lost).
let rendered = "";

function render(force = false) {
  if (!session) return;
  const stamp = JSON.stringify([session, sandboxUp, llm, ssh && [ssh.ok, ssh.keys, ssh.message], session.ai.state === "running" ? Math.floor(Date.now() / 1000) : 0]);
  if (!force && stamp === rendered) return;
  rendered = stamp;
  renderOverview();
  refreshViews();
  trackOutput();
  refreshStatusBar();
  refreshTitle();
  bus.emit("session", session);
}

function renderOverview() {
  const view = tabs.get("overview").view;
  const s = session.summary;
  const css = s.overall === "FAIL" ? "FAIL" : s.overall === "PASS" ? "PASS" : s.overall === "NOT RUN" ? "none" : "review";
  const step = (done, text) => h("li", { class: done ? "done" : "" }, `${done ? "✔" : "○"} ${text}`);
  const row = (name, c) => h("tr", {}, h("td", {}, name), ...ORDER.map((k) => h("td", {}, c[k])));
  view.replaceChildren(...[
    h("h1", {}, session.repo ? (session.repo.name || session.repo.url) : "No repository yet"),
    session.repo && h("div", { class: "meta" }, `${session.repo.url} · ${session.repo.path} · ${session.repo.commit} ${session.repo.subject} — ${session.repo.author}`),
    session.ai.state === "running" && aiOverview(),   // pinned to the top while it works
    h("div", { class: `verdict-badge ${css}` }, s.overall),
    decidedNote(s) && h("div", { class: "meta" }, decidedNote(s)),
    s.reason && h("div", { class: "meta" }, s.reason),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, ""), ...ORDER.map((k) => h("th", {}, SHORT[k])))),
      h("tbody", {}, row("mandatory", s.mandatory), row("bonus", s.bonus))),
    h("ol", { class: "steps" },
      step(session.subjects.length > 0, "Add the subject PDFs (Upload PDFs or Library…)"),
      step(!!session.repo, "Clone the repository"),
      step(session.results.length > 0, "Run checks")),
    session.ai.state !== "running" && aiOverview(),
    session.state === "done" && h("p", { class: "meta" },
      s.decided_by === "claude" ? "Claude has the final say on the result, and what it found replaces what the scripts reported."
        : "FAIL when anything is lacking, PASS WITH ISSUES when something still needs a second look, PASS when both lists in verdict.md are empty. Once claude's review is merged, its decision sets the result."),
  ].filter((node) => node != null && node !== false));   // optional parts are false/null when absent: never show them as text
}

function fmtDuration(ms) {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function aiLog(ai, open) {
  if (!ai.progress.length) return null;
  const start = Date.parse(ai.started_at || ai.progress[0].at);
  return h("details", { class: "ai-log", open },
    h("summary", {}, open ? "Activity" : `Activity log (${ai.progress.length} steps)`),
    h("ol", {}, ai.progress.map((e) => h("li", {}, h("span", { class: "t" }, `+${fmtDuration(Date.parse(e.at) - start)}`), " ", e.text))));
}

function aiOverview() {
  const ai = session.ai;
  if (ai.state === "running") {
    const now = Date.now();
    const last = ai.progress.length ? Date.parse(ai.progress[ai.progress.length - 1].at) : Date.parse(ai.started_at);
    const silent = Math.round((now - last) / 1000);
    return h("div", { class: "ai-box" },
      h("div", { class: "ai-head" },
        h("h2", {}, "AI review in progress ", h("span", { class: "tag" }, "AI")),
        h("span", { class: "timer" }, fmtDuration(now - Date.parse(ai.started_at))),
        h("button", { onclick: () => guarded(async () => setSession(await post(`sessions/${sid}/ai/cancel`))) }, "Stop")),
      h("p", { class: "step" }, ai.step || "Starting…"),
      silent >= 20 && h("p", { class: "meta" }, `No news from the server for ${silent}s. Free models can take a few minutes; a request is given up after 5 minutes, and a temporary error is retried automatically. You can stop at any time.`),
      aiLog(ai, true));
  }
  if (ai.state === "error") return h("div", { class: "ai-box error" }, h("strong", {}, "AI review failed: "), ai.message, aiLog(ai, false));
  if (ai.state === "cancelled") return h("div", { class: "ai-box" }, h("strong", {}, "AI review stopped. "), "Nothing was changed.", aiLog(ai, false));
  const ov = ai.overview;
  if (ai.state !== "done" || !ov) return null;
  return h("div", { class: "ai-box" },
    h("h2", {}, "What is in the repository ", h("span", { class: "tag" }, "AI")),
    h("p", { class: "meta" }, `Written by ${ai.model} from a bounded view of the files. Advisory and unverified; it never changes the result. ` +
      `${ai.input_tokens.toLocaleString()} tokens in, ${ai.output_tokens.toLocaleString()} out.`),
    ov.purpose && h("p", {}, ov.purpose),
    ov.languages.length > 0 && h("p", {}, h("strong", {}, "Languages: "), ov.languages.join(", ")),
    ov.build_and_run && h("p", {}, h("strong", {}, "Build and run: "), ov.build_and_run),
    ov.components.length > 0 && h("table", { class: "components" }, h("tbody", {}, ov.components.map((c) =>
      h("tr", {}, h("td", {}, h("button", { class: "ev", onclick: () => guarded(() => openFile(c.path)) }, c.path)), h("td", {}, c.role))))),
    ov.notable.length > 0 && h("div", {}, h("strong", {}, "Notable"), h("ul", {}, ov.notable.map((x) => h("li", {}, x)))),
    ov.not_found.length > 0 && h("div", {}, h("strong", {}, "Required by the subject but not found"), h("ul", {}, ov.not_found.map((x) => h("li", {}, x)))),
    ai.not_fully_sent.length > 0 && h("p", { class: "meta" }, `${ai.not_fully_sent.length} file(s) were cut or left out of what the model saw.`),
    aiLog(ai, false));
}

const ASSESSMENT = { likely_ok: ["likely ok", "ok"], likely_problem: ["likely a problem", "bad"], unclear: ["unclear", "unclear"], not_applicable: ["not applicable", "na"] };

function aiReviewNodes(r) {
  const review = r.rule_id && session.ai.reviews ? session.ai.reviews[r.rule_id] : null;
  if (!review) return { chip: null, body: [] };
  const [label, kind] = ASSESSMENT[review.assessment] ?? [review.assessment, "unclear"];   // never fail on a status we do not know
  return {
    chip: h("span", { class: `ai-chip ${kind}` }, `${review.by || "AI"}: ${label}`),
    body: [h("div", { class: "ai-review" },
      review.finding && h("div", {}, review.finding),
      review.why_manual && h("div", { class: "src-ref" }, "Check by hand: " + review.why_manual),
      review.evidence.map((e) => h("button", { class: "ev", onclick: () => guarded(() => openFile(e.file, e.line)) }, `${e.file}:${e.line}`)),
      h("div", { class: "src-ref" }, `${review.by === "Claude" ? "Claude" : "AI"}-generated, unverified`))],
  };
}

// Show a saved review everywhere: the tree, the verdict tab, a message.
async function afterReviewSaved(result) {
  session = await api(`sessions/${sid}`);
  render();
  await loadTree();
  await refreshVerdict(false);
  if (result && result.warning) return toast(result.warning);
  const claude = session.claude || {};
  if (!claude.structured) {
    return toast(`claude's report was added to ${session.verdict_file || "verdict.md"} as text: it has no data block at the end, so it could not be merged into the lists. ${(claude.problems || [])[0] || ""}`);
  }
  const gaps = claude.assessed < claude.total ? ` ${claude.total - claude.assessed} requirement(s) were not answered.` : "";
  const fixes = (claude.fixes || []).length ? ` ${claude.fixes.length} correction(s) listed.` : "";
  toast(`Merged claude's answers (${claude.assessed} of ${claude.total} requirements) into ${session.verdict_file || "verdict.md"}.${fixes}${gaps}`, true);
}

// Type the review request into a claude that is already running: as one bracketed paste, then Enter.
function pasteIntoTerminal(terminal, text) {
  for (let i = 0; i < text.length; i += 8000) terminal.send({ t: "i", d: (i === 0 ? "\x1b[200~" : "") + text.slice(i, i + 8000) + (i + 8000 >= text.length ? "\x1b[201~" : "") });
  setTimeout(() => terminal.send({ t: "i", d: "\r" }), 500);
}

async function reviewInTerminal() {
  closeDialog();
  const existing = tabs.get("terminal");
  const live = existing?.session;
  if (live && live.socket && live.socket.readyState === WebSocket.OPEN) {
    const { text } = await api(`sessions/${sid}/review-prompt`);
    showTab("terminal");
    pasteIntoTerminal(live, text);
    return;
  }
  if (existing) { existing.keep = true; closeTab("terminal"); }   // not connected: a fresh claude begins with the prompt (the server replaces the old one)
  const { id } = await post(`sessions/${sid}/terminal-prompt`);
  await openTerminal(id);
}

async function startAi() {
  const files = session.repo ? session.repo.path : "the repository";
  const background = () => guarded(async () => { closeDialog(); setSession(await post(`sessions/${sid}/ai`)); showTab("overview"); poll(); });
  if (llm.provider === "claude-cli") {
    const envLine = h("p", { class: "hint" }, "Checking the environment…");
    environmentHint(envLine);
    dialog("Ask claude to review what the checks could not?", h("div", {},
      envLine,
      h("p", {}, "claude will receive a prompt built from this run: what the scripts verified (so it does not redo it), and everything they ",
        h("strong", {}, "could not"), " judge: the subject requirements that need a human, plus correctness, error handling, memory, design and readability."),
      h("p", {}, "It runs in the terminal: you watch it work, it asks before running anything, and you can answer or ask follow-up questions."),
      h("p", { class: "hint" }, `The source files of ${files} are read by claude and sent to Anthropic using your Claude login. It works on a throw-away copy, never on the original. It has the final say: what it finds replaces what the scripts reported, and its decision sets the result.`)), [
      h("button", { onclick: closeDialog }, "Cancel"),
      h("button", { class: "primary", onclick: () => guarded(reviewInTerminal) }, "Run"),
    ]);
    return;
  }
  dialog("Send this repository to an AI model?", h("div", {},
    h("p", {}, `The source files of ${files} (up to about 100,000–150,000 characters) and the manual-review sentences from the subjects will be sent to `,
      h("strong", {}, llm.host), ` using the model `, h("strong", {}, llm.model), "."),
    llm.provider === "openai" && h("p", { class: "warning" },
      `${llm.host} is a server you configured, not necessarily the model's maker. It receives the student's code and forwards it, so check who runs it and how it handles data.`),
    h("p", { class: "hint" }, "The student's code leaves this computer. Its answers count in the result (a requirement it judges a problem makes it FAIL), and every file and line it cites is checked against what it was shown.")), [
    h("button", { onclick: closeDialog }, "Cancel"),
    h("button", { class: "primary", onclick: background }, "Send and review"),
  ]);
}

// A prompt that asks an AI to fix what the review found. It is shown to copy rather than sent to the claude tab, because that
// claude works on a throw-away copy: a fix made there would be gone when the tab closes.
async function openFixPrompt() {
  const { text, must_fix: mustFix, look_at: lookAt, bonus } = await api(`sessions/${sid}/fix-prompt`);
  if (!text) return toast("Nothing to fix: no check failed and nothing needs a second look.", true);
  const box = h("textarea", { class: "prompt", spellcheck: "false" });
  box.value = text;
  const copy = async () => {
    try { await navigator.clipboard.writeText(box.value); } catch {
      box.select();
      if (!document.execCommand("copy")) return toast("Could not copy: select the text and press Ctrl/Cmd+C.");
    }
    toast("Prompt copied.", true);
  };
  dialog("Prompt to fix what the review found", h("div", {},
    h("p", {}, `${mustFix} to fix, ${lookAt} to look at${bonus ? `, ${bonus} in the bonus part` : ""}. Paste it into claude (or any assistant) in the project's own folder. You can edit it first.`),
    box,
    h("p", { class: "hint" }, "It is not run here: the claude tab works on a throw-away copy, so a fix made there would be lost when the tab closes.")), [
    h("button", { onclick: closeDialog }, "Close"),
    h("button", { class: "primary", onclick: () => guarded(copy) }, "Copy"),
  ]);
}

// ------------------------------------------------------------------ the lists of the panel: checklist, improvements, subject rules

const expanded = new Set();

// The checklist follows verdict.md: a requirement claude (or the AI) has judged moves to where verdict.md lists it.
const REVIEWED_STATUS = { likely_problem: "fail", unclear: "manual", likely_ok: "pass", not_applicable: "pass" };

function shownStatus(r) {
  const review = r.status === "manual" && r.rule_id && session.ai.reviews ? session.ai.reviews[r.rule_id] : null;
  return review ? (REVIEWED_STATUS[review.assessment] ?? "manual") : r.status;
}

function renderChecks() {
  if (!session.results.length) {
    return h("p", { class: "hint" }, session.state === "running" ? "Running…" : "No results yet. Add subjects, clone a repository and press Run checks.");
  }
  const out = h("div");
  for (const status of ORDER) {
    if (!shown.has(status)) continue;
    const items = session.results.filter((r) => shownStatus(r) === status);
    if (!items.length) continue;
    out.append(h("div", { class: "group-title" }, `${TITLES[status]} (${items.length})`));
    for (const r of items) out.append(resultItem(r));
  }
  return out;
}

function resultItem(r) {
  const key = `${r.rule_id}|${r.title}|${r.detail}`;
  const ai = aiReviewNodes(r);
  const body = h("div", { class: "item-body", hidden: !expanded.has(key) },
    ai.body,
    r.sources.length > 0 && h("div", { class: "src-ref" }, "From ", r.sources.slice(0, 4).flatMap((s, i) => [i ? ", " : "", pageLink(s.pdf, s.page)])),
    r.evidence.map((e) => h("button", { class: "ev", onclick: () => guarded(() => openFile(e.file, e.line)) },
      e.line ? `${e.file}:${e.line}` : e.file, e.snippet && h("span", { class: "snip" }, e.snippet))),
    r.log && h("pre", { class: "log" }, r.log));
  const expandable = r.sources.length || r.evidence.length || r.log || ai.body.length;
  return h("div", { class: `item st-${shownStatus(r)}` },
    h("div", { class: "item-head", onclick: () => {
      if (!expandable) return;
      body.hidden = !body.hidden;
      body.hidden ? expanded.delete(key) : expanded.add(key);
    } },
      h("span", { class: "icon" }, ICON[shownStatus(r)]),
      h("span", { class: "item-title" }, r.title, r.section === "bonus" ? " [bonus]" : ""),
      ai.chip,
      r.by === "Claude" && h("span", { class: "ai-chip na" }, "Claude"),
      h("span", { class: "item-detail" }, r.detail)),
    expandable && body);
}


const CATEGORY_LABELS = { structure: "Structure", code: "Code", logic: "Logic", readability: "Readability" };

function renderImprovements() {
  if (!session.results.length) return h("p", { class: "hint" }, "Run the checks to get improvement suggestions.");
  const out = h("div");
  const readme = session.readme || {};
  out.append(h("div", { class: `readme-note ${readme.present ? "ok" : "missing"}` },
    readme.present ? `README: ${readme.name} found (${readme.lines} non-empty lines)` : "README: no README found in this repository"));
  if (!session.improvements.length) return (out.append(h("p", { class: "hint" }, "No improvement suggestions.")), out);
  for (const [category, label] of Object.entries(CATEGORY_LABELS)) {
    const items = session.improvements.filter((i) => i.category === category);
    if (!items.length) continue;
    out.append(h("div", { class: "group-title" }, `${label} (${items.length})`));
    for (const item of items) {
      const key = `imp|${item.category}|${item.title}`;
      const body = h("div", { class: "item-body", hidden: !expanded.has(key) },
        item.detail && h("div", {}, item.detail),
        item.evidence.map((e) => h("button", { class: "ev", onclick: () => guarded(() => openFile(e.file, e.line)) },
          e.line ? `${e.file}:${e.line}` : e.file, e.snippet && h("span", { class: "snip" }, e.snippet))));
      out.append(h("div", { class: "item" },
        h("div", { class: "item-head", onclick: () => { body.hidden = !body.hidden; body.hidden ? expanded.delete(key) : expanded.add(key); } },
          h("span", { class: `prio prio-${item.priority}` }, item.priority),
          h("span", { class: "item-title" }, item.title, item.source === "ai" ? " (AI)" : ""),
          h("span", { class: "item-detail" }, item.detail.slice(0, 140))),
        body));
    }
  }
  return out;
}

function renderRules() {
  if (!session.subjects.length) return h("p", { class: "hint" }, "No subjects loaded.");
  const out = h("div");
  for (const s of session.subjects) {
    out.append(h("div", { class: "group-title" }, s.kind === "norm"
      ? `${s.name} — the Norm, added because C code was detected (${s.rules.length} rules)`
      : `${s.name} — ${[TRACK_LABEL[s.track], `${s.rules.length} rules`, s.lang ? s.lang.toUpperCase() : "language unknown"].filter(Boolean).join(", ")}`));
    for (const r of s.rules) {
      const auto = r.kind !== "manual";
      out.append(h("div", { class: `item st-${auto ? "pass" : "manual"}` },
        h("div", { class: "item-head" },
          h("span", { class: "icon" }, auto ? "⚙" : "?"),
          h("span", { class: "item-title" }, r.title, r.unit !== "." ? ` (${r.unit})` : "", r.section === "bonus" ? " [bonus]" : ""),
          h("span", { class: "item-detail" }, r.text.slice(0, 200)))));
    }
  }
  return out;
}

async function refreshVerdict(show) {
  if (!session.results.length) return;
  const text = await (await fetch(`/api/sessions/${sid}/verdict.md`)).text();
  let tab = tabs.get("verdict.md");
  const before = activeTab;
  if (!tab) {
    addTab("verdict.md", "verdict.md", h("div", { class: "view doc" }), false);
    tab = tabs.get("verdict.md");
    Object.assign(tab, { kind: "markdown", language: "Markdown", iconEl: () => fileIcon(iconFor("verdict.md")) });
  }
  const where = session.repo && session.verdict_file ? `${session.repo.path}/${session.verdict_file}` : null;
  tab.view.replaceChildren(
    h("div", { class: "doc-bar" },
      where ? h("span", {}, "Saved in the repository as ", h("code", {}, where)) : h("span", {}, "Not saved into the repository"),
      h("button", { onclick: () => runCommand("verdict.downloadVerdict") }, "⬇ Download")),
    renderMarkdown(text));
  if (show) showTab("verdict.md");
  else if (before && before !== "verdict.md" && tabs.has(before)) showTab(before);        // (a tab added is shown: give the foreground back)
}


// ------------------------------------------------------------------ environment check (sandbox + claude's terminal)

function environmentTable(title, part) {
  const rows = part.tools.map((t) => h("tr", { class: t.ok ? "ok" : (t.required ? "bad" : "warn") },
    h("td", { class: "mark" }, t.ok ? "✔" : (t.required ? "✖" : "–")), h("td", {}, t.name), h("td", { class: "detail" }, t.detail)));
  return h("div", { class: "env-part" }, h("h4", {}, title),
    part.available ? h("table", { class: "env" }, h("tbody", {}, rows)) : h("p", { class: "warning" }, part.error || "Not available."));
}

function environmentSummary(env) {
  const issues = [];
  for (const [label, part] of [["sandbox", env.sandbox], ["claude's terminal", env.terminal]]) {
    if (!part.available) { issues.push(`${label}: ${part.error || "not available"}`); continue; }
    const s = part.summary;
    if (!s.basics_ok) issues.push(`${label}: ${s.failed.filter((n) => !n.startsWith("docker")).join(", ")} not working`);
    if (s.docker_daemon_down) issues.push(`${label}: Docker client is there but no daemon answers, so a student's Dockerfile cannot be built or run`);
    else if (!s.docker_ok) issues.push(`${label}: ${s.failed.filter((n) => n.startsWith("docker")).join(", ")} not working`);
  }
  return issues;
}

// Always the full check: make, C and C++, the Docker daemon, and building and running a tiny Dockerfile.
async function openEnvironment() {
  const status = h("div", {}, h("p", { class: "hint" },
    "Compiling and running a C and a C++ program through make, then building and running a tiny Dockerfile… "
    + "(about a minute the first time: it downloads a base image)"));
  dialog("Environment check", status, [h("button", { onclick: closeDialog }, "Close")]);
  let env;
  try { env = await api("environment?deep=true"); } catch (err) { status.replaceChildren(h("p", { class: "warning" }, err.message)); return; }
  const issues = environmentSummary(env);
  status.replaceChildren(
    env.ready
      ? h("p", { class: "env-ok" }, `✅ Ready. The sandbox and claude's terminal can compile C and C++, run make and use Docker${env.deep ? ", and build and run a Dockerfile" : ""}.`)
      : h("div", { class: "warning" }, h("strong", {}, "Not ready:"), h("ul", {}, issues.map((i) => h("li", {}, i)))),
    environmentTable("Sandbox (builds and runs the checks)", env.sandbox),
    environmentTable("Claude's terminal (where claude works)", env.terminal),
    h("p", { class: "hint" }, "Only ✖ items stop the environment from being ready. Anything extra a project needs should come from the Dockerfile the student ships."));
  $("#dialog .buttons").replaceChildren(
    h("button", { onclick: closeDialog }, "Close"),
    h("button", { onclick: () => guarded(openEnvironment) }, "Run again"));
}

// One line inside the review dialog, so a missing tool is seen before claude starts.
async function environmentHint(line) {
  try {
    const env = await api("environment");
    const issues = environmentSummary(env);
    line.className = env.ready ? "env-ok" : "warning";
    line.replaceChildren(env.ready ? "✅ Environment ready: make, C, C++ and Docker all work for claude."
      : `⚠ Environment problem: ${issues.join("; ")}. `, h("button", { class: "linklike", onclick: () => guarded(openEnvironment) }, "Details"));
  } catch { line.textContent = ""; }
}

// ------------------------------------------------------------------ dialogs: upload, library, open a project

const pdfsOf = (files) => [...files].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
let lastTrack = (() => { try { return localStorage.getItem("verdict.track") || ""; } catch { return ""; } })();
let pendingTrack = "";

async function uploadFiles(pdfs, track) {
  if (!pdfs.length) return toast("Only PDF files can be added.");
  const form = new FormData();
  pdfs.forEach((f) => form.append("files", f));
  form.append("track", track);
  setSession(await api(`sessions/${sid}/subjects`, { method: "POST", body: form }));
  toast(`Added, and kept in samples/${track}/: ${pdfs.map((f) => f.name).join(", ")}`, true);
}

// Every upload is kept in the library, in the folder of the track it belongs to.
async function openUpload(files = null) {
  const pdfs = files && pdfsOf(files);
  if (pdfs && !pdfs.length) return toast("Only PDF files can be added.");
  const lib = await api("library");
  const radios = lib.tracks.map((t) => h("label", { class: "pick" },
    h("input", { type: "radio", name: "track", value: t.id, checked: t.id === lastTrack }), t.label,
    h("span", { class: "dim" }, `samples/${t.id}/`)));
  const go = () => {
    const track = radios.map((r) => r.firstChild).find((i) => i.checked)?.value;
    if (!track) return toast("Choose Common Core, Post Common Core or RNCP first.");
    lastTrack = track;
    try { localStorage.setItem("verdict.track", track); } catch { /* storage unavailable */ }
    closeDialog();
    if (pdfs) guarded(() => uploadFiles(pdfs, track));
    else { pendingTrack = track; $("#file-input").click(); }
  };
  dialog("Upload subject PDFs", h("div", {},
    pdfs && h("div", { class: "where" }, pdfs.map((f) => h("div", {}, f.name))),
    h("p", {}, "Where does this subject belong?"),
    radios,
    h("p", { class: "dim" }, "It is added to this review and kept in that library folder.")), [
    h("button", { onclick: closeDialog }, "Cancel"),
    h("button", { class: "primary", onclick: go }, pdfs ? "Upload" : "Choose PDFs…"),
  ]);
}

async function openLibrary() {
  const lib = await api("library");
  if (!lib.items.length) return toast(`The library is empty. Put PDFs in ${lib.tracks.map((t) => `samples/${t.id}/`).join(", ")}.`);
  const have = new Set(session.subjects.map((s) => s.name));
  const boxes = [];
  // One collapsible folder per track; a folder opens by itself when it holds subjects already in this review.
  const groups = lib.tracks.map((t) => {
    const mine = lib.items.filter((i) => i.track === t.id).map((i) => h("label", { class: "pick" },
      h("input", { type: "checkbox", value: i.path, "data-name": i.name, checked: have.has(i.name) }), i.name));
    boxes.push(...mine);
    const count = h("span", { class: "dim" });
    const recount = () => {
      const ticked = mine.filter((b) => b.firstChild.checked).length;
      count.textContent = mine.length ? `${mine.length} PDF${mine.length === 1 ? "" : "s"}${ticked ? ` · ${ticked} selected` : ""}` : "empty";
    };
    mine.forEach((b) => b.firstChild.addEventListener("change", recount));
    recount();
    return h("details", { class: "track", open: mine.some((b) => b.firstChild.checked) },
      h("summary", {}, h("span", {}, t.label), count),
      h("div", { class: "track-items" }, mine.length ? mine : h("p", { class: "dim" }, `Empty: put PDFs in samples/${t.id}/`)));
  });
  dialog("Add subjects from the library", h("div", {}, groups,
    h("p", { class: "dim" }, lib.norm ? "The Norm (samples/en.norm.pdf) is added by itself whenever C code is detected."
      : "samples/en.norm.pdf is missing, so the Norm cannot be added to C projects.")), [
    h("button", { onclick: closeDialog }, "Cancel"),
    h("button", { class: "primary", onclick: () => guarded(async () => {
      const paths = boxes.map((b) => b.firstChild).filter((c) => c.checked && !have.has(c.dataset.name)).map((c) => c.value);
      closeDialog();
      if (paths.length) setSession(await post(`sessions/${sid}/subjects/library`, { paths }));
    }) }, "Add"),
  ]);
}

async function openClone() {
  const projects = await api("projects").catch(() => ({ root: "projects" }));
  const existing = await api("projects/existing").catch(() => ({ folders: [] }));
  await refreshSsh();
  const nameFromUrl = (url) => {
    const last = url.trim().replace(/\/+$/, "").split(/[/:]/).pop().replace(/\.git$/, "");
    return /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(last) ? last : "";
  };
  const field = (label, input, hint) => h("div", { class: "field" }, h("label", {}, label), input, hint && h("div", { class: "hint" }, hint));
  const url = h("input", { type: "text", placeholder: "git@github.com:user/repo.git", value: session.repo?.url ?? "" });
  const name = h("input", { type: "text", placeholder: "project name" });
  const where = h("div", { class: "where" });
  let nameEdited = false;
  const update = () => {
    if (!nameEdited) name.value = nameFromUrl(url.value);
    where.textContent = `Will clone to ${projects.root}/${name.value.trim()}`;
  };
  name.addEventListener("input", () => { nameEdited = true; update(); });
  url.addEventListener("input", update);
  const submit = (endpoint, payload) => {
    closeDialog();
    session.state = "cloning"; render();
    guarded(async () => {
      try {
        setSession(await post(`sessions/${sid}/${endpoint}`, payload));
        resetForNewProject();
        await loadTree();
      } catch (err) {
        session = await api(`sessions/${sid}`); render();
        throw err;
      }
    });
  };
  const go = () => submit("repo", { url: url.value, name: name.value });
  for (const input of [url, name]) input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") go(); });

  // An existing folder in the projects folder, reviewed where it is.
  let chosen = session.repo?.path ?? "";
  const filter = h("input", { type: "text", placeholder: "filter folders" });
  const list = h("div", { class: "track-items folder-list" });
  const fill = () => {
    const needle = filter.value.trim().toLowerCase();
    const rows = existing.folders.filter((f) => f.path.toLowerCase().includes(needle)).map((f) => {
      const radio = h("input", { type: "radio", name: "existing-folder", value: f.path });
      radio.checked = f.path === chosen;
      radio.addEventListener("change", () => { chosen = f.path; });
      return h("label", { class: "pick" }, radio, h("span", {}, f.path), h("span", { class: "dim" }, f.git ? "git repository" : "folder"));
    });
    list.replaceChildren(...(rows.length ? rows : [h("p", { class: "dim" }, existing.folders.length
      ? "No folder matches."
      : `No folders yet. Put the project inside the projects folder on your computer (./${projects.root}), then reopen this dialog.`)]));
  };
  filter.addEventListener("input", fill);
  const useExisting = () => chosen ? submit("repo/existing", { path: chosen }) : toast("Choose a folder first.");

  const show = (mode) => {
    const tab = (id, label) => h("button", { class: mode === id ? "active" : "", onclick: () => show(id) }, label);
    const switcher = h("div", { class: "md-bar" }, tab("clone", "Clone with SSH"), tab("existing", "Use an existing folder"));
    if (mode === "clone") {
      dialog("Open a project", h("div", {}, switcher,
        ssh && !ssh.ok && h("div", { class: "warning" }, "SSH is not ready: ", ssh.message),
        field("Repository (SSH)", url),
        field("Project name", name),
        where), [
        h("button", { onclick: closeDialog }, "Cancel"),
        h("button", { class: "primary", onclick: go }, "Clone"),
      ]);
      update();
      url.focus();
    } else {
      fill();
      dialog("Open a project", h("div", {}, switcher,
        h("p", { class: "dim" }, `Reviews a folder that is already in ${projects.root}/. Nothing is cloned, copied or deleted; the verdict is saved inside that folder.`),
        filter, list), [
        h("button", { onclick: closeDialog }, "Cancel"),
        h("button", { class: "primary", onclick: useExisting }, "Use this folder"),
      ]);
      filter.focus();
    }
  };
  show(existing.folders.length && !session.repo?.url && session.repo ? "existing" : "clone");
}

// A different project: nothing of the old one stays on the page (its files, its changes, its search, its shells).
function resetForNewProject() {
  for (const key of [...tabs.keys()]) if (key !== "overview") closeTab(key);
  killAllTerminals();
  clearSearch();
  scm.data = null;
  scm.collapsed.clear();
  expanded.clear();
  render(true);
}

function clearSearch() {
  searchState.results = null;
  searchState.query = "";
  searchState.error = "";
  const spec = viewSpecs.get("search");
  if (spec?.input) spec.input.value = "";
  if (spec?.results) renderSearch();
}

// Every run starts from nothing. The server ends claude and drops its report and every review, removes the old verdict.md and pulls
// the project before the checks begin; here go the windows that showed the old run: claude's tab, the verdict, the open files and
// changes, the search results, and the lists on the side are read again.
function clearForNewRun() {
  const claude = tabs.get("terminal");
  if (claude) { claude.discard = true; closeTab("terminal"); }
  closeTab("verdict.md");
  for (const [key, tab] of [...tabs]) if (tab.repoFile || tab.kind === "diff") closeTab(key);           // (their contents are from before the pull)
  clearSearch();
  expanded.clear();
  shown.clear();
  for (const k of ORDER) shown.add(k);
  render(true);
}

async function run() {
  if (!session.repo) return toast("Clone a repository first.");
  if (!session.subjects.length) return toast("Add at least one subject PDF first.");
  setSession(await post(`sessions/${sid}/run`));
  clearForNewRun();
  showTab("overview");
  loadTree().catch(() => {});                                                    // (verdict.md is gone; the pull may bring more)
  loadScm({ force: true });
  logOutput("Checks", "— a new run starts from nothing —");
  poll();
}

async function poll() {
  if (polling) return;
  polling = true;
  try {
    while (true) {
      session = await api(`sessions/${sid}`);
      render();
      if (session.state !== "running" && session.ai.state !== "running") break;
      await new Promise((r) => setTimeout(r, 1000));
    }
    loadTree();
    if (session.state === "done") await refreshVerdict(true);
    renderOverview();
  } finally { polling = false; }
}
