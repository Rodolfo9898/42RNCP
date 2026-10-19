"use strict";

// Everything shown comes from untrusted input (PDFs, repositories): build DOM with
// textContent only, never innerHTML.

const $ = (sel, root = document) => root.querySelector(sel);

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const ICON = { fail: "✖", warn: "!", manual: "?", skipped: "–", pass: "✔" };
const ORDER = ["fail", "warn", "manual", "skipped", "pass"];
const SHORT = { fail: "Failed", warn: "Warnings", manual: "Manual", skipped: "Skipped", pass: "Passed" };
const TITLES = { fail: "Failed", warn: "Warnings", manual: "Needs manual review", skipped: "Not checked", pass: "Passed" };

let sid = null;
let session = null;
let sandboxUp = false;
let llm = { configured: false, model: "" };
let ssh = null;
let panelTab = "checks";
let activeTab = "overview";
const tabs = new Map(); // key -> { title, view, closable }
const shown = new Set(ORDER);
let polling = false;

async function api(path, options = {}) {
  const res = await fetch(`/api/${path}`, options);
  if (!res.ok) {
    let message = res.statusText;
    try { message = (await res.json()).detail || message; } catch { /* not JSON */ }
    throw new Error(message);
  }
  return res.json();
}
const post = (path, body) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}),
});

function toast(message, ok = false) {
  const el = $("#toast");
  el.classList.toggle("ok", ok);
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.hidden = true; }, 6000);
}

async function guarded(fn) {
  try { return await fn(); } catch (err) { toast(err.message); }
}

// ------------------------------------------------------------------ session

async function init() {
  sid = new URLSearchParams(location.search).get("session") || localStorage.getItem("verdict.session");
  if (sid) {
    try { session = await api(`sessions/${sid}`); } catch { sid = null; }
  }
  if (!sid) {
    session = await post("sessions");
    sid = session.id;
    localStorage.setItem("verdict.session", sid);
  }
  const health = await api("health").catch(() => ({}));
  sandboxUp = health.sandbox === true;
  llm = health.llm || llm;
  refreshSsh();
  addTab("overview", "Verdict", h("div", { class: "view overview" }), false);
  showTab("overview");
  render();
  loadTree();
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

function render() {
  renderSidebar();
  renderOverview();
  renderPanel();
  const repo = session.repo;
  $("#st-repo").textContent = repo ? `${repo.path || repo.url} @ ${repo.commit}` : "no repository";
  $("#st-ssh").textContent = ssh ? (ssh.ok ? `ssh: ${ssh.keys.length} key(s)` : "ssh: ⚠ not ready") : "";
  $("#st-ssh").title = ssh ? ssh.message : "";
  $("#st-sandbox").textContent = sandboxUp ? "sandbox: ready" : "sandbox: unavailable (static checks only)";
  const label = session.ai.state === "running" ? `AI review: ${session.ai.step || "starting"}`
    : { idle: "ready", cloning: "cloning…", running: "running checks…", done: "done", error: "error" }[session.state];
  $("#st-state").textContent = session.message ? `${label}: ${session.message}` : label;
  $("#statusbar").classList.toggle("busy", busy());
  $("#btn-run").disabled = busy();
  const ai = $("#btn-ai");
  $("#btn-terminal").disabled = !session.repo;
  ai.disabled = busy() || !session.results.length || !llm.configured;
  ai.title = !llm.configured ? "Not configured: set ANTHROPIC_API_KEY, or LLM_BASE_URL + LLM_API_KEY + LLM_MODEL, in .env (see the README)"
    : !session.results.length ? "Run the checks first"
    : "Ask an AI model to describe the repository and weigh the manual-review items";
  ai.textContent = session.ai.state === "running" ? "✨ AI working…" : "✨ AI review";
  $("#btn-clone").disabled = busy();
}

function renderSidebar() {
  const list = $("#subjects");
  list.replaceChildren(...session.subjects.map((s) => h("li", { title: `${s.rules.length} rules extracted` },
    h("span", { class: "name" }, s.name),
    h("span", { class: "meta" }, `${s.rules.length} rules`),
    h("button", { class: "x", title: "Remove", onclick: () => guarded(async () => setSession(
      await api(`sessions/${sid}/subjects/${encodeURIComponent(s.name)}`, { method: "DELETE" }))) }, "✕"))));
  $("#subjects-count").textContent = session.subjects.length || "";
  $("#subjects-hint").hidden = session.subjects.length > 0;
}

function renderOverview() {
  const view = tabs.get("overview").view;
  const s = session.summary;
  const css = s.overall === "FAIL" ? "FAIL" : s.overall === "PASS" ? "PASS" : s.overall === "NOT RUN" ? "none" : "review";
  const step = (done, text) => h("li", { class: done ? "done" : "" }, `${done ? "✔" : "○"} ${text}`);
  const row = (name, c) => h("tr", {}, h("td", {}, name), ...ORDER.map((k) => h("td", {}, c[k])));
  view.replaceChildren(
    h("h1", {}, session.repo ? (session.repo.name || session.repo.url) : "No repository yet"),
    session.repo && h("div", { class: "meta" }, `${session.repo.url} · ${session.repo.path} · ${session.repo.commit} ${session.repo.subject} — ${session.repo.author}`),
    session.ai.state === "running" && aiOverview(),   // pinned to the top while it works
    h("div", { class: `verdict-badge ${css}` }, s.overall),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, ""), ...ORDER.map((k) => h("th", {}, SHORT[k])))),
      h("tbody", {}, row("mandatory", s.mandatory), row("bonus", s.bonus))),
    h("ol", { class: "steps" },
      step(session.subjects.length > 0, "Add the subject PDFs (Upload PDFs or Library…)"),
      step(!!session.repo, "Clone the repository"),
      step(session.results.length > 0, "Run checks")),
    session.ai.state !== "running" && aiOverview(),
    session.state === "done" && h("p", { class: "meta" },
      "Automated checks cover what a script can verify. “Needs manual review” items come from the subject and still need a human."),
  );
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


async function saveClaudeReview() {
  const result = await post(`sessions/${sid}/claude-review/save`);
  await afterReviewSaved(result);
}

// Show a saved review everywhere: the tree (the new file), the verdict tab, a message.
async function afterReviewSaved(result) {
  session = await api(`sessions/${sid}`);
  render();
  await loadTree();
  await refreshVerdict(false);
  if (result && result.warning) return toast(result.warning);
  const claude = session.claude || {};
  if (!claude.structured) {
    return toast(`claude's report is in the repository, but it has no data block at the end, so it could not be merged into the lists. ${(claude.problems || [])[0] || ""}`);
  }
  const files = [session.verdict_file, session.claude_review_file].filter(Boolean).join(" and ");
  const gaps = claude.assessed < claude.total ? ` ${claude.total - claude.assessed} requirement(s) were not answered.` : "";
  toast(`Merged claude's answers (${claude.assessed} of ${claude.total} requirements) into ${session.verdict_file || "verdict.md"}; full report: ${session.claude_review_file || "claude-review.md"}.${gaps}`, true);
}

// Type the review request into a claude that is already running: as one bracketed paste, then Enter.
function pasteIntoTerminal(tab, text) {
  for (let i = 0; i < text.length; i += 8000) tab.send({ t: "i", d: (i === 0 ? "\x1b[200~" : "") + text.slice(i, i + 8000) + (i + 8000 >= text.length ? "\x1b[201~" : "") });
  setTimeout(() => tab.send({ t: "i", d: "\r" }), 500);
}

async function reviewInTerminal() {
  closeDialog();
  const existing = tabs.get("terminal");
  if (existing && existing.socket && existing.socket.readyState === WebSocket.OPEN) {
    const { text } = await api(`sessions/${sid}/review-prompt`);
    showTab("terminal");
    pasteIntoTerminal(existing, text);
    return;
  }
  if (existing) closeTab("terminal");               // a dead session: start a fresh claude that begins with the prompt
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
      h("p", {}, h("strong", {}, "In the terminal: "), "you watch it work, it asks before running anything, and you can answer or ask follow-up questions."),
      h("p", {}, h("strong", {}, "In the background: "), "it reads the repository silently with read-only tools and adds its answer to verdict.md."),
      h("p", { class: "hint" }, `The source files of ${files} are read by claude and sent to Anthropic using your Claude login. It works on a throw-away copy, never on the original. The AI only advises: the pass/fail result is unchanged.`)), [
      h("button", { onclick: closeDialog }, "Cancel"),
      h("button", { onclick: background }, "Run in the background"),
      h("button", { class: "primary", onclick: () => guarded(reviewInTerminal) }, "Review in the terminal"),
    ]);
    return;
  }
  dialog("Send this repository to an AI model?", h("div", {},
    h("p", {}, `The source files of ${files} (up to about 100,000–150,000 characters) and the manual-review sentences from the subjects will be sent to `,
      h("strong", {}, llm.host), ` using the model `, h("strong", {}, llm.model), "."),
    llm.provider === "openai" && h("p", { class: "warning" },
      `${llm.host} is a server you configured, not necessarily the model's maker. It receives the student's code and forwards it, so check who runs it and how it handles data.`),
    h("p", { class: "hint" }, "The student's code leaves this computer. The AI only advises: it never changes the pass/fail result, and every file and line it cites is checked against what it was shown.")), [
    h("button", { onclick: closeDialog }, "Cancel"),
    h("button", { class: "primary", onclick: background }, "Send and review"),
  ]);
}

function renderPanel() {
  for (const b of document.querySelectorAll("#panel-tabs > button")) b.classList.toggle("active", b.dataset.tab === panelTab);
  const counts = Object.fromEntries(ORDER.map((k) => [k, session.results.filter((r) => r.status === k).length]));
  $("#filters").replaceChildren(...ORDER.map((k) => h("button", {
    class: `chip ${shown.has(k) ? "on" : ""}`, title: `Toggle ${TITLES[k].toLowerCase()}`,
    onclick: () => { shown.has(k) ? shown.delete(k) : shown.add(k); renderPanel(); },
  }, `${ICON[k]} ${counts[k]}`)));
  $("#filters").hidden = panelTab !== "checks";
  const imp = $('#panel-tabs [data-tab="improvements"]');
  imp.textContent = session.improvements.length ? `Improvements (${session.improvements.length})` : "Improvements";
  const body = $("#panel-body");
  const keepScroll = body.scrollTop;
  body.replaceChildren(panelTab === "checks" ? renderChecks() : panelTab === "improvements" ? renderImprovements() : renderRules());
  body.scrollTop = keepScroll;
}

const expanded = new Set();

function renderChecks() {
  if (!session.results.length) {
    return h("p", { class: "hint" }, session.state === "running" ? "Running…" : "No results yet. Add subjects, clone a repository and press Run checks.");
  }
  const out = h("div");
  for (const status of ORDER) {
    if (!shown.has(status)) continue;
    const items = session.results.filter((r) => r.status === status);
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
    r.sources.length > 0 && h("div", { class: "src-ref" }, "From " + r.sources.slice(0, 4).map((s) => `${s.pdf} p.${s.page}`).join(", ")),
    r.evidence.map((e) => h("button", { class: "ev", onclick: () => guarded(() => openFile(e.file, e.line)) },
      e.line ? `${e.file}:${e.line}` : e.file, e.snippet && h("span", { class: "snip" }, e.snippet))),
    r.log && h("pre", { class: "log" }, r.log));
  const expandable = r.sources.length || r.evidence.length || r.log || ai.body.length;
  return h("div", { class: `item st-${r.status}` },
    h("div", { class: "item-head", onclick: () => {
      if (!expandable) return;
      body.hidden = !body.hidden;
      body.hidden ? expanded.delete(key) : expanded.add(key);
    } },
      h("span", { class: "icon" }, ICON[r.status]),
      h("span", { class: "item-title" }, r.title, r.section === "bonus" ? " [bonus]" : ""),
      ai.chip,
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
    out.append(h("div", { class: "group-title" }, `${s.name} — ${s.rules.length} rules, ${s.lang ? s.lang.toUpperCase() : "language unknown"}`));
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


// ------------------------------------------------------------------ markdown (safe: DOM nodes only)

function inlineMarkdown(source) {
  const out = [];
  let buffer = "";
  const flush = () => { if (buffer) { out.push(buffer); buffer = ""; } };
  let i = 0;
  while (i < source.length) {
    const c = source[i];
    if (c === "\\" && i + 1 < source.length) { buffer += source[i + 1]; i += 2; continue; }
    if (c === "`") {
      const ticks = source.slice(i).match(/^`+/)[0];
      const end = source.indexOf(ticks, i + ticks.length);
      if (end > -1) {
        flush();
        out.push(h("code", {}, source.slice(i + ticks.length, end).trim()));
        i = end + ticks.length;
        continue;
      }
    }
    if (source.startsWith("**", i)) {
      const end = source.indexOf("**", i + 2);
      if (end > -1) { flush(); out.push(h("strong", {}, inlineMarkdown(source.slice(i + 2, end)))); i = end + 2; continue; }
    }
    if (c === "_" && (i === 0 || /\s|\(/.test(source[i - 1])) && source[i + 1] && !/\s/.test(source[i + 1])) {
      let end = i + 1;
      while ((end = source.indexOf("_", end)) > -1 && (source[end - 1] === "\\" || /\s/.test(source[end - 1]))) end++;
      if (end > -1) { flush(); out.push(h("em", {}, inlineMarkdown(source.slice(i + 1, end)))); i = end + 1; continue; }
    }
    buffer += c;
    i++;
  }
  flush();
  return out;
}

function renderMarkdown(text) {
  const root = h("div", { class: "markdown" });
  const lines = text.split("\n");
  const isItem = (l) => /^\s*- /.test(l);
  const fenceOf = (l) => (l.match(/^\s*(`{3,})\s*$/) || [])[1];
  const takeFence = (start) => {
    const fence = fenceOf(lines[start]);
    const body = [];
    let j = start + 1;
    while (j < lines.length && !(fenceOf(lines[j]) && fenceOf(lines[j]).length >= fence.length)) body.push(lines[j++].replace(/^ {0,2}/, ""));
    return { node: h("pre", { class: "log" }, body.join("\n")), next: j + 1 };
  };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim() || line.startsWith("<!--")) { i++; continue; }
    if (fenceOf(line)) { const { node, next } = takeFence(i); root.append(node); i = next; continue; }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) { root.append(h(`h${heading[1].length}`, {}, inlineMarkdown(heading[2]))); i++; continue; }
    if (line.startsWith("|") && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
      const cells = (l) => l.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim());
      const head = cells(line);
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].startsWith("|")) rows.push(cells(lines[i++]));
      root.append(h("table", {}, h("thead", {}, h("tr", {}, head.map((c) => h("th", {}, inlineMarkdown(c))))),
        h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, inlineMarkdown(c))))))));
      continue;
    }
    if (line.startsWith(">")) {
      const quote = [];
      while (i < lines.length && lines[i].startsWith(">")) quote.push(lines[i++].replace(/^>\s?/, ""));
      root.append(h("blockquote", {}, inlineMarkdown(quote.join(" "))));
      continue;
    }
    if (isItem(line)) {
      const top = h("ul");
      const stack = [{ depth: 0, list: top, last: null }];
      while (i < lines.length && (isItem(lines[i]) || (fenceOf(lines[i]) && stack.at(-1).last))) {
        if (fenceOf(lines[i])) { const { node, next } = takeFence(i); stack.at(-1).last.append(node); i = next; continue; }
        const depth = Math.floor(lines[i].match(/^\s*/)[0].length / 2);
        const li = h("li", {}, inlineMarkdown(lines[i].replace(/^\s*- /, "")));
        while (stack.length > 1 && stack.at(-1).depth > depth) stack.pop();
        if (depth > stack.at(-1).depth && stack.at(-1).last) {
          const sub = h("ul");
          stack.at(-1).last.append(sub);
          stack.push({ depth, list: sub, last: null });
        }
        stack.at(-1).list.append(li);
        stack.at(-1).last = li;
        i++;
        while (i < lines.length && !lines[i].trim() && isItem(lines[i + 1] || "")) i++;
      }
      root.append(top);
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !isItem(lines[i]) && !/^(#{1,4}\s|>|\||`{3})/.test(lines[i])) para.push(lines[i++]);
    root.append(h("p", {}, inlineMarkdown(para.join(" "))));
  }
  return root;
}

async function refreshVerdict(show) {
  if (!session.results.length) return;
  const text = await (await fetch(`/api/sessions/${sid}/verdict.md`)).text();
  let tab = tabs.get("verdict.md");
  if (!tab) {
    addTab("verdict.md", "verdict.md", h("div", { class: "view doc" }), false);
    tab = tabs.get("verdict.md");
  }
  const where = session.repo && session.verdict_file ? `${session.repo.path}/${session.verdict_file}` : null;
  tab.view.replaceChildren(
    h("div", { class: "doc-bar" },
      where ? h("span", {}, "Saved in the repository as ", h("code", {}, where)) : h("span", {}, "Not saved into the repository"),
      h("button", { onclick: () => { window.location.href = `/api/sessions/${sid}/verdict.md?download=true`; } }, "⬇ Download")),
    renderMarkdown(text));
  if (show) showTab("verdict.md"); else showTab(activeTab);
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

async function openEnvironment(deep = false) {
  const status = h("div", {}, h("p", { class: "hint" }, deep
    ? "Building and running a tiny Dockerfile… this can take a minute (it downloads a base image)."
    : "Compiling and running a C and a C++ program through make, and asking the Docker daemon… (a few seconds)"));
  dialog("Environment check", status, [h("button", { onclick: closeDialog }, "Close")]);
  let env;
  try { env = await api(`environment?deep=${deep}`); } catch (err) { status.replaceChildren(h("p", { class: "warning" }, err.message)); return; }
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
    h("button", { onclick: () => guarded(() => openEnvironment(false)) }, "Run again"),
    h("button", { class: env.deep ? "" : "primary", onclick: () => guarded(() => openEnvironment(true)) }, "Also test a docker build (needs internet)"));
}

// One line inside the review dialog, so a missing tool is seen before claude starts.
async function environmentHint(line) {
  try {
    const env = await api("environment");
    const issues = environmentSummary(env);
    line.className = env.ready ? "env-ok" : "warning";
    line.replaceChildren(env.ready ? "✅ Environment ready: make, C, C++ and Docker all work for claude."
      : `⚠ Environment problem: ${issues.join("; ")}. `, h("button", { class: "linklike", onclick: () => guarded(() => openEnvironment(false)) }, "Details"));
  } catch { line.textContent = ""; }
}

// ------------------------------------------------------------------ claude terminal (xterm.js <-> PTY in the terminal container)

async function openTerminal(promptId) {
  if (!session.repo) return toast("Clone a repository first.");
  if (typeof Terminal === "undefined" || typeof FitAddon === "undefined") return toast("The terminal files failed to load.");
  const existing = tabs.get("terminal");
  if (existing) return showTab("terminal");

  const status = await api("terminal").catch(() => ({ configured: false }));
  const view = h("div", { class: "view term" });
  const holder = h("div", { class: "term-holder" });
  view.append(h("div", { class: "term-bar" },
    h("span", {}, "claude saves its report as ", h("code", {}, "claude-review.md"), " (approve the write). It is copied into the repository next to verdict.md automatically."),
    h("button", { onclick: () => guarded(saveClaudeReview) }, "💾 Save review to verdict.md")), holder);
  addTab("terminal", "⌨ claude", view, true);
  tabs.get("terminal").onClose = () => {
    clearInterval(tabs.get("terminal")?.watcher);
    tabs.get("terminal")?.socket?.close();
    tabs.get("terminal")?.term?.dispose();
    // The server collects the saved report as the terminal closes; show it once it has.
    setTimeout(async () => { session = await api(`sessions/${sid}`); render(); loadTree(); refreshVerdict(false).catch(() => {}); }, 2000);
  };
  showTab("terminal");

  const term = new Terminal({
    cursorBlink: true, fontSize: 13, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    theme: { background: "#1e1e1e", foreground: "#cccccc", cursor: "#cccccc" }, scrollback: 5000, convertEol: false,
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(holder);
  const tab = tabs.get("terminal");
  tab.term = term;
  fit.fit();

  if (!status.configured || !status.reachable) {
    term.writeln("\x1b[33mThe terminal service is not running.\x1b[0m Start everything with \x1b[1mmake run\x1b[0m, then reopen this tab.");
    return;
  }
  if (!status.claude) term.writeln("\x1b[33mclaude is not installed in the terminal container.\x1b[0m Rebuild with \x1b[1mmake re\x1b[0m.");

  const send = (event) => { if (tab.socket && tab.socket.readyState === WebSocket.OPEN) tab.socket.send(JSON.stringify(event)); };
  tab.send = send;
  const connect = () => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const withPrompt = promptId && !tab.promptUsed ? `&prompt=${encodeURIComponent(promptId)}` : "";   // only the first connection carries it
    tab.promptUsed = true;
    const socket = new WebSocket(`${scheme}://${location.host}/api/sessions/${sid}/terminal?cols=${term.cols}&rows=${term.rows}${withPrompt}`);
    socket.binaryType = "arraybuffer";
    tab.socket = socket;
    socket.onmessage = (ev) => term.write(typeof ev.data === "string" ? ev.data : new Uint8Array(ev.data));
    socket.onclose = () => {
      if (tab.socket !== socket) return;
      term.writeln("\r\n\x1b[2m[disconnected — press Enter to reconnect]\x1b[0m");
      tab.disconnected = true;
    };
  };
  term.onData((data) => {
    if (tab.disconnected) { tab.disconnected = false; term.clear(); connect(); return; }
    send({ t: "i", d: data });
  });
  term.onResize(({ cols, rows }) => send({ t: "r", c: cols, r: rows }));
  new ResizeObserver(() => { if (!view.hidden) { try { fit.fit(); } catch { /* not laid out yet */ } } }).observe(holder);
  let known = session.claude_review_at || "";
  tab.watcher = setInterval(async () => {
    try {
      const latest = await api(`sessions/${sid}`);
      if ((latest.claude_review_at || "") !== known && latest.claude_review_file) {
        known = latest.claude_review_at || "";
        await afterReviewSaved({ verdict_file: latest.verdict_file });
      }
    } catch { /* offline or restarting: try again next time */ }
  }, 4000);
  term.writeln("\x1b[2mFirst time? Type /login inside claude to sign in with your Claude account.\x1b[0m");
  term.focus();
  connect();
}

// ------------------------------------------------------------------ tabs & files

function addTab(key, title, view, closable = true) {
  tabs.set(key, { title, view, closable });
  $("#views").append(view);
}

function showTab(key) {
  activeTab = key;
  for (const [k, t] of tabs) t.view.hidden = k !== key;
  $("#st-lang").textContent = tabs.get(key)?.language ?? "";
  document.body.classList.toggle("term-focus", key === "terminal");   // the terminal gets the full height
  if (key === "terminal") requestAnimationFrame(() => { tabs.get("terminal")?.term?.focus(); window.dispatchEvent(new Event("resize")); });
  $("#tabs").replaceChildren(...[...tabs].map(([k, t]) => h("div", { class: `tab ${k === key ? "active" : ""}`, onclick: () => showTab(k) },
    t.title, t.closable && h("span", { class: "close", onclick: (ev) => { ev.stopPropagation(); closeTab(k); } }, "×"))));
  document.querySelectorAll(".tree .row").forEach((row) => row.classList.toggle("active", row.dataset.path === key));
}

function closeTab(key) {
  const tab = tabs.get(key);
  if (tab.onClose) tab.onClose();
  tab.view.remove();
  tabs.delete(key);
  showTab(activeTab === key ? "overview" : activeTab);
}

// Highlighted files arrive as [class, text] pairs per line; build spans with textContent only.
function sourceNodes(file, lines) {
  if (!file.tokens || file.tokens.length !== lines.length) return [file.content];
  const nodes = [];
  file.tokens.forEach((line, i) => {
    for (const [cls, text] of line) nodes.push(cls ? h("span", { class: `t-${cls}` }, text) : text);
    if (i < file.tokens.length - 1) nodes.push("\n");
  });
  return nodes;
}

async function openFile(path, line) {
  let tab = tabs.get(path);
  if (!tab) {
    const file = await api(`sessions/${sid}/file?path=${encodeURIComponent(path)}`);
    const view = h("div", { class: "view" });
    if (file.binary) view.append(h("div", { class: "notice" }, `${path} is a binary file (${file.size} bytes).`));
    else {
      const lines = file.content.split("\n");
      if (file.truncated) view.append(h("div", { class: "notice" }, "File truncated to 1 MB."));
      view.append(h("div", { class: "code" },
        h("div", { class: "gutter" }, lines.map((_, i) => i + 1).join("\n")),
        h("pre", { class: "src" }, ...sourceNodes(file, lines))));
    }
    addTab(path, path.split("/").pop(), view);
    tab = tabs.get(path);
    tab.language = file.language || (file.binary ? "binary" : "plain text");
  }
  showTab(path);
  tab.view.querySelectorAll(".hl").forEach((n) => n.remove());
  const code = $(".code", tab.view);
  if (line && code) {
    code.append(h("div", { class: "hl at", style: `top:${4 + (line - 1) * 20}px` }));
    tab.view.scrollTop = Math.max(0, (line - 1) * 20 - tab.view.clientHeight / 2);
  }
}

async function loadTree() {
  const entries = await api(`sessions/${sid}/tree`).catch(() => []);
  const root = $("#tree");
  $("#tree-hint").hidden = entries.length > 0;
  const nodes = new Map([["", h("div", { class: "children" })]]);
  const mk = (entry) => {
    const name = entry.path.split("/").pop();
    const depth = entry.path.split("/").length - 1;
    const pad = `padding-left:${8 + depth * 12}px`;
    if (entry.type === "dir") {
      const kids = h("div", { class: "children", hidden: depth > 0 });
      nodes.set(entry.path, kids);
      const twisty = h("span", { class: "twisty" }, depth > 0 ? "▸" : "▾");
      const row = h("div", { class: "row", style: pad, onclick: () => {
        kids.hidden = !kids.hidden;
        twisty.textContent = kids.hidden ? "▸" : "▾";
      } }, twisty, name);
      return [h("div", {}, row, kids)];
    }
    return [h("div", { class: "row", style: pad, "data-path": entry.path, onclick: () => guarded(() => openFile(entry.path)) },
      h("span", { class: "twisty" }, ""), name)];
  };
  // Directories first within each folder, as in VS Code.
  const sorted = [...entries].sort((a, b) => {
    const pa = a.path.split("/"), pb = b.path.split("/");
    for (let i = 0; i < Math.min(pa.length, pb.length); i++) {
      if (pa[i] !== pb[i]) {
        const aDir = i < pa.length - 1 || a.type === "dir", bDir = i < pb.length - 1 || b.type === "dir";
        if (aDir !== bDir) return aDir ? -1 : 1;
        return pa[i].localeCompare(pb[i]);
      }
    }
    return pa.length - pb.length;
  });
  for (const entry of sorted) {
    const parent = entry.path.includes("/") ? entry.path.slice(0, entry.path.lastIndexOf("/")) : "";
    const [node] = mk(entry);
    (nodes.get(parent) ?? nodes.get("")).append(node);
  }
  root.replaceChildren(nodes.get(""));
}

// ------------------------------------------------------------------ actions

function dialog(title, body, buttons) {
  const d = $("#dialog");
  d.replaceChildren(h("h3", {}, title), body, h("div", { class: "buttons" }, buttons));
  $("#modal").hidden = false;
}
const closeDialog = () => { $("#modal").hidden = true; };

async function uploadFiles(files) {
  const pdfs = [...files].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
  if (!pdfs.length) return toast("Only PDF files can be added.");
  const form = new FormData();
  pdfs.forEach((f) => form.append("files", f));
  setSession(await api(`sessions/${sid}/subjects`, { method: "POST", body: form }));
}

async function openLibrary() {
  const items = await api("library");
  if (!items.length) return toast("The library is empty. Put PDFs in the samples/ folder.");
  const have = new Set(session.subjects.map((s) => s.name));
  const boxes = items.map((i) => h("label", { class: "pick" },
    h("input", { type: "checkbox", value: i.name, checked: have.has(i.name) }), i.name));
  dialog("Add subjects from the library", h("div", {}, boxes), [
    h("button", { onclick: closeDialog }, "Cancel"),
    h("button", { class: "primary", onclick: () => guarded(async () => {
      const names = boxes.map((b) => b.firstChild).filter((c) => c.checked && !have.has(c.value)).map((c) => c.value);
      closeDialog();
      if (names.length) setSession(await post(`sessions/${sid}/subjects/library`, { names }));
    }) }, "Add"),
  ]);
}

async function openClone() {
  const projects = await api("projects").catch(() => ({ root: "projects", folders: [] }));
  await refreshSsh();
  const nameFromUrl = (url) => {
    const last = url.trim().replace(/\/+$/, "").split(/[/:]/).pop().replace(/\.git$/, "");
    return /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(last) ? last : "";
  };
  const field = (label, input, hint) => h("div", { class: "field" }, h("label", {}, label), input, hint && h("div", { class: "hint" }, hint));
  const url = h("input", { type: "text", placeholder: "git@github.com:user/repo.git", value: session.repo?.url ?? "" });
  const name = h("input", { type: "text", placeholder: "project name" });
  const dest = h("input", { type: "text", list: "dest-list", placeholder: "(top level)" });
  const where = h("div", { class: "where" });
  let nameEdited = false;
  const update = () => {
    if (!nameEdited) name.value = nameFromUrl(url.value);
    const rel = [dest.value.trim().replace(/^\/+|\/+$/g, ""), name.value.trim()].filter(Boolean).join("/");
    where.textContent = `Will clone to ${projects.root}/${rel}`;
  };
  name.addEventListener("input", () => { nameEdited = true; update(); });
  url.addEventListener("input", update);
  dest.addEventListener("input", update);
  const go = () => {
    closeDialog();
    session.state = "cloning"; render();
    guarded(async () => {
      try {
        setSession(await post(`sessions/${sid}/repo`, { url: url.value, name: name.value, destination: dest.value }));
        for (const k of [...tabs.keys()]) if (k !== "overview") closeTab(k);
        await loadTree();
      } catch (err) {
        session = await api(`sessions/${sid}`); render();
        throw err;
      }
    });
  };
  for (const input of [url, name, dest]) input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") go(); });
  dialog("Clone a repository", h("div", {},
    ssh && !ssh.ok && h("div", { class: "warning" }, "SSH is not ready: ", ssh.message),
    field("Repository (SSH)", url),
    field("Project name", name),
    field("Destination folder", dest, `A folder inside the ${projects.root} folder. Existing folders are suggested; a new one is created if needed.`),
    h("datalist", { id: "dest-list" }, projects.folders.map((f) => h("option", { value: f }))),
    where), [
    h("button", { onclick: closeDialog }, "Cancel"),
    h("button", { class: "primary", onclick: go }, "Clone"),
  ]);
  update();
  url.focus();
}

async function run() {
  if (!session.repo) return toast("Clone a repository first.");
  if (!session.subjects.length) return toast("Add at least one subject PDF first.");
  setSession(await post(`sessions/${sid}/run`));
  showTab("overview");
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

$("#btn-upload").onclick = () => $("#file-input").click();
$("#file-input").onchange = (ev) => { guarded(() => uploadFiles(ev.target.files)); ev.target.value = ""; };
$("#btn-library").onclick = () => guarded(openLibrary);
$("#btn-env").onclick = () => guarded(() => openEnvironment(false));
$("#btn-clone").onclick = () => guarded(openClone);
$("#btn-run").onclick = () => guarded(run);
$("#btn-ai").onclick = () => guarded(startAi);
$("#btn-terminal").onclick = () => guarded(openTerminal);
$("#btn-export").onclick = () => {
  if (!session.results.length) return toast("Run the checks first.");
  window.location.href = `/api/sessions/${sid}/verdict.md?download=true`;
};
$("#modal").addEventListener("click", (ev) => { if (ev.target.id === "modal") closeDialog(); });
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeDialog(); });
for (const b of document.querySelectorAll("#panel-tabs > button")) b.onclick = () => { panelTab = b.dataset.tab; renderPanel(); };

const side = $("#sidebar");
side.addEventListener("dragover", (ev) => { ev.preventDefault(); side.classList.add("drag"); });
side.addEventListener("dragleave", () => side.classList.remove("drag"));
side.addEventListener("drop", (ev) => {
  ev.preventDefault(); side.classList.remove("drag");
  guarded(() => uploadFiles(ev.dataTransfer.files));
});

init().catch((err) => toast(err.message));
