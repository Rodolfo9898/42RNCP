"use strict";

// Terminals. claude's is a tab of the editor area. The shells are terminals of the Terminal view in the panel, as in VS Code: several can be
// open (tabs on the right), and each can be split into panes side by side or one above the other. Every shell is a real shell on the server
// (the terminal service keeps it under the name of its pane), and it survives a reload of the page.

const terminalSessions = new Map();     // pane (or "claude") -> TerminalSession
let terminals = termNew();              // the groups and panes (model.js)
let terminalHost = null;                // the element of the Terminal view
let renamingPane = null;

function termTheme() {
  const css = getComputedStyle(document.documentElement);
  const pick = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
  return { background: pick("--terminal-bg", "#1e1e1e"), foreground: pick("--terminal-fg", "#cccccc"), cursor: pick("--terminal-cursor", "#cccccc"), selectionBackground: pick("--terminal-selection", "#264f78") };
}

const terminalLibrariesLoaded = () => typeof Terminal !== "undefined" && typeof FitAddon !== "undefined";

// One xterm.js on one PTY of the terminal service. It reconnects by itself when the connection drops (the PTY keeps running).
class TerminalSession {
  constructor({ kind, pane = "", name, promptId = null, hints = [], onEnded = null }) {
    this.kind = kind;
    this.pane = pane;
    this.name = name;
    this.promptId = promptId;
    this.hints = hints;
    this.onEnded = onEnded;
    this.socket = null;
    this.attempts = 0;
    this.closing = false;
    this.disconnected = false;
    this.keep = false;           // closing the tab does not end claude (it is being replaced)
    this.discard = false;        // ... and its report is not collected (a new run starts)
    this.element = h("div", { class: "terminal-holder" });
    this.opened = false;
    this.status = null;
  }

  async start() {
    this.status = await api("terminal").catch(() => ({ configured: false }));
    if (!terminalLibrariesLoaded()) { this.element.append(h("p", { class: "hint" }, "The terminal files failed to load.")); return this; }
    const s = settings;
    this.term = new Terminal({
      cursorBlink: s.get("terminal.integrated.cursorBlinking"), cursorStyle: s.get("terminal.integrated.cursorStyle"), fontSize: s.get("terminal.integrated.fontSize") * zoomFactor(),
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", theme: termTheme(), scrollback: s.get("terminal.integrated.scrollback"), convertEol: false,
    });
    this.fitAddon = new FitAddon.FitAddon();
    this.term.loadAddon(this.fitAddon);
    this.term.open(this.element);
    this.opened = true;
    this.fit();
    if (!this.status.configured || !this.status.reachable) {
      this.term.writeln("\x1b[33mThe terminal service is not running.\x1b[0m Start everything with \x1b[1mmake run\x1b[0m, then open the terminal again.");
      return this;
    }
    if (!this.status.claude && this.kind === "claude") this.term.writeln("\x1b[33mclaude is not installed in the terminal container.\x1b[0m Rebuild with \x1b[1mmake re\x1b[0m.");
    this.term.onData((data) => {
      if (this.disconnected) { this.disconnected = false; this.term.clear(); this.connect(); return; }
      this.send({ t: "i", d: data });
    });
    this.term.onResize(({ cols, rows }) => this.send({ t: "r", c: cols, r: rows }));
    this.term.onSelectionChange?.(() => { if (settings.get("terminal.integrated.copyOnSelection") && this.term.hasSelection()) copyText(this.term.getSelection(), "the selection"); });
    this.resizeObserver = new ResizeObserver(() => this.fit());
    this.resizeObserver.observe(this.element);
    for (const line of this.hints) this.term.writeln(line);
    this.connect();
    return this;
  }

  send(event) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(event));
  }

  url() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const base = `${scheme}://${location.host}/api/sessions/${sid}/terminal?cols=${this.term.cols}&rows=${this.term.rows}`;
    if (this.kind === "shell") return `${base}&kind=shell&pane=${encodeURIComponent(this.pane)}`;
    const withPrompt = this.promptId && !this.promptUsed ? `&prompt=${encodeURIComponent(this.promptId)}` : "";         // only the first connection carries it
    this.promptUsed = true;
    return base + withPrompt;
  }

  connect() {
    const socket = new WebSocket(this.url());
    socket.binaryType = "arraybuffer";
    this.socket = socket;
    socket.onmessage = (ev) => this.term.write(typeof ev.data === "string" ? ev.data : new Uint8Array(ev.data));
    socket.onopen = () => { this.attempts = 0; };
    socket.onclose = (ev) => {
      if (this.socket !== socket || this.closing) return;
      // 4410: claude (or the shell) itself ended. 4411: opened in another tab. 4429: too many. Anything else is a dropped connection:
      // it is still running on the server, so reconnect by itself and carry on where it was.
      if (![4410, 4411, 4429].includes(ev.code) && (this.attempts += 1) <= 30) {
        if (this.attempts === 1) this.term.writeln("\r\n\x1b[2m[connection lost, reconnecting…]\x1b[0m");
        this.retry = setTimeout(() => { this.term.reset(); this.connect(); }, Math.min(1000 * this.attempts, 5000));         // the server replays the screen
        return;
      }
      const why = ev.code === 4410 ? `${this.name} ended` : ev.code === 4411 ? "opened in another tab" : ev.code === 4429 ? "too many terminals are open" : "disconnected";
      this.term.writeln(`\r\n\x1b[2m[${why} — press Enter to start again]\x1b[0m`);
      this.disconnected = true;
      if (ev.code === 4410) this.onEnded?.(this);
    };
  }

  fit() {
    if (!this.opened || !this.element.isConnected || !this.element.offsetParent && !this.element.clientHeight) return;
    try { this.fitAddon.fit(); } catch { /* not laid out yet */ }
  }

  focus() { this.term?.focus(); }

  // Take the terminal out of the page. `end`: also stop it on the server (closing a terminal on purpose does; a reload does not).
  dispose({ end = true } = {}) {
    this.closing = true;
    clearTimeout(this.retry);
    this.resizeObserver?.disconnect();
    this.socket?.close();
    if (end && !this.keep && !this.discard) fetch(`/api/sessions/${sid}/${this.kind === "shell" ? `shell/end?pane=${encodeURIComponent(this.pane)}` : "terminal/end"}`, { method: "POST" }).catch(() => {});
    this.term?.dispose();
    this.element.remove();
  }
}

// ------------------------------------------------------------------ claude: a tab of the editor area

// kind "claude": claude on the project (or a throw-away copy of it). kind "shell" is a terminal of the panel.
async function openTerminal(promptId, kind = "claude") {
  if (!session.repo) return notify("Clone a repository first.", { level: "warning" });
  if (kind === "shell") return newTerminal();
  if (!terminalLibrariesLoaded()) return notify("The terminal files failed to load.", { level: "error" });
  const existing = tabs.get("terminal");
  if (existing) { showTab("terminal"); return existing; }

  const status = await api("terminal").catch(() => ({ configured: false }));
  const live = status.workdir === "live";            // claude works in the project folder itself, not in a copy
  const project = `projects/${session.repo.path}`;
  const gitNote = ` ${sshNote(status.ssh === true)}`;
  const bar = h("div", { class: "term-bar" }, h("span", {}, (live
    ? `claude works directly in your project (${project}): every change it makes is on your machine at once. Its report is merged into verdict.md automatically.`
    : "claude works in a throw-away copy of your project: nothing it changes goes back to your project. Its report is merged into verdict.md automatically.") + gitNote));
  const claude = new TerminalSession({
    kind: "claude", name: "claude", promptId,
    hints: ["\x1b[2mFirst time? Type /login inside claude to sign in with your Claude account.\x1b[0m"],
  });
  const view = h("div", { class: "view term" }, bar, claude.element);
  addTab("terminal", "claude", view, true);
  const tab = tabs.get("terminal");
  Object.assign(tab, { kind: "terminal", session: claude, iconEl: () => icon("terminal", 14), moveToPanel: null });
  tab.onClose = () => {
    clearInterval(tab.watcher);
    clearInterval(tab.treeWatcher);
    // Closing the tab ends claude on purpose. (A reload or a lost connection does not: the session keeps running.)
    // (A new run closes claude's tab itself: the server has already ended it and dropped its report, so nothing is collected.)
    claude.keep = !!tab.keep;
    claude.discard = !!tab.discard;
    claude.dispose();
    if (tab.discard) return;
    // The server collects the saved report as the terminal closes; show it once it has.
    setTimeout(async () => { session = await api(`sessions/${sid}`); render(); loadTree(); refreshVerdict(false).catch(() => {}); }, 2000);
  };
  showTab("terminal");
  await claude.start();
  // Working in the project itself: files appear, change and disappear under the tree, so keep the tree up to date while this tab is open.
  if (live) tab.treeWatcher = setInterval(() => { if (!document.hidden) loadTree().catch(() => {}); }, 5000);
  let known = session.claude_review_at || "";
  tab.watcher = setInterval(async () => {
    try {
      const latest = await api(`sessions/${sid}`);
      if ((latest.claude_review_at || "") !== known) {
        known = latest.claude_review_at || "";
        await afterReviewSaved({ verdict_file: latest.verdict_file });
      }
    } catch { /* offline or restarting: try again next time */ }
  }, 4000);
  claude.focus();
  return tab;
}

// ------------------------------------------------------------------ the shells of the panel

const terminalPlaceholderNeeded = () => !termPanes(terminals).length;

function saveTerminals() {
  if (sid) store.set(`verdict.terminals:${sid}`, { groups: terminals.groups, active: terminals.active, titles: terminals.titles, nextGroup: terminals.nextGroup, nextPane: terminals.nextPane });
}

function restoreTerminalModel() {
  const saved = store.get(`verdict.terminals:${sid}`, null);
  if (!saved || !Array.isArray(saved.groups)) return;
  const ok = saved.groups.every((g) => isRecord(g) && typeof g.id === "string" && g.grid && gridLeaves(g.grid).every((p) => /^t\d+$/.test(p)));
  if (!ok) return;
  terminals = { ...termNew(), groups: saved.groups, active: saved.active ?? saved.groups[0]?.id ?? null, titles: isRecord(saved.titles) ? saved.titles : {}, nextGroup: saved.nextGroup ?? saved.groups.length + 1, nextPane: saved.nextPane ?? 1 };
}

// What the server still runs (a reloaded page) is shown again, and what it no longer runs is forgotten. Only the terminals remembered by this
// browser can be forgotten: one made while the server was being asked is not running yet, and must not go with them.
let adoption = null;

const MAX_SHELL_PANES = 8;           // (what the terminal service allows for one review: a ninth would only be refused there)
const tooManyShells = () => termPanes(terminals).length >= MAX_SHELL_PANES && (notify(`At most ${MAX_SHELL_PANES} terminals can be open for a review. Kill one first.`, { level: "warning" }), true);

function adoptRunningShells() {
  if (adoption || !sid) return adoption;
  restoreTerminalModel();
  const remembered = new Set(termPanes(terminals));
  adoption = api(`sessions/${sid}/shells`).catch(() => ({ panes: [], claude: false })).then((running) => {
    const named = running.panes.filter((p) => p);
    let next = terminals;
    for (const pane of termPanes(next)) if (remembered.has(pane) && !named.includes(pane)) next = termKill(next, pane);
    terminals = termAdopt(next, named);
    saveTerminals();
    renderTerminalView();
  });
  return adoption;
}

async function newTerminal() {
  if (!session.repo) return notify("Clone a repository first.", { level: "warning" });
  showTerminalView();                                                // (builds the view, which first looks at what the server runs)
  await adoption;
  if (tooManyShells()) return null;
  const { state, pane } = termAdd(terminals);
  terminals = state;
  saveTerminals();
  renderTerminalView();
  focusPane(pane);
  return pane;
}

async function splitTerminal(side = "right") {
  showTerminalView();
  await adoption;
  const pane = termActivePane(terminals);
  if (!pane) return newTerminal();
  if (tooManyShells()) return null;
  const { state, pane: fresh } = termSplit(terminals, pane, side);
  terminals = state;
  saveTerminals();
  renderTerminalView();
  focusPane(fresh);
  return fresh;
}

function killTerminal(pane = termActivePane(terminals)) {
  if (!pane) return;
  terminalSessions.get(pane)?.dispose();
  terminalSessions.delete(pane);
  terminals = termKill(terminals, pane);
  saveTerminals();
  renderTerminalView();
  const next = termActivePane(terminals);
  if (next) focusPane(next);
  bus.emit("terminals");
}

function focusPane(pane) {
  terminals = termFocus(terminals, pane);
  saveTerminals();
  renderTerminalView();
  requestAnimationFrame(() => terminalSessions.get(pane)?.focus());
}

function showTerminalView() {
  setLayout(layoutRevealView(layout, "terminals"));
}

function renameTerminal(pane) {
  renamingPane = pane;
  renderTerminalView();
}

function cycleTerminal(step) {
  const ids = terminals.groups.map((g) => g.id);
  if (ids.length < 2) return;
  const at = ids.indexOf(terminals.active);
  const group = terminals.groups.find((g) => g.id === ids[(at + step + ids.length) % ids.length]);
  focusPane(group.active);
}

// The next terminal of the group on show (the panes side by side).
function cyclePane(step) {
  const group = terminals.groups.find((g) => g.id === terminals.active);
  if (!group) return;
  const leaves = gridLeaves(group.grid);
  if (leaves.length < 2) return;
  focusPane(leaves[(leaves.indexOf(group.active) + step + leaves.length) % leaves.length]);
}

// A new project: every shell of the old one ends.
function killAllTerminals() {
  for (const pane of termPanes(terminals)) {
    terminalSessions.get(pane)?.dispose();
    terminalSessions.delete(pane);
  }
  terminals = termNew();
  saveTerminals();
  renderTerminalView();
}

function focusPaneDirection(direction) {
  const next = termFocusDirection(terminals, direction);
  if (next) focusPane(next);
}

// A shell as a tab of the editor area (Move Terminal into Editor Area), and back.
function moveTerminalToEditor(pane = termActivePane(terminals)) {
  const sess = terminalSessions.get(pane);
  if (!sess) return;
  const key = `shell:${pane}`;
  const title = terminals.titles[pane] || "zsh";
  const view = h("div", { class: "view term" }, h("div", { class: "term-bar" }, h("span", {}, `A shell of the panel, moved here. ${sshNote(sess.status?.ssh === true)}`)), sess.element);
  terminals = termKill(terminals, pane);
  terminalSessions.delete(pane);
  saveTerminals();
  addTab(key, title, view, true);
  const tab = tabs.get(key);
  Object.assign(tab, { kind: "terminal", session: sess, iconEl: () => icon("terminal", 14), pane });
  tab.onClose = () => { sess.dispose(); };
  tab.moveToPanel = () => moveTerminalToPanel(key);
  renderTerminalView();
  showTab(key);
  requestAnimationFrame(() => { sess.fit(); sess.focus(); });
}

function moveTerminalToPanel(key) {
  const tab = tabs.get(key);
  if (!tab || !tab.session) return;
  const sess = tab.session;
  tab.onClose = null;
  const pane = tab.pane;
  tab.view.remove();
  tabs.delete(key);
  const at = tabHistory.indexOf(key);
  if (at >= 0) tabHistory.splice(at, 1);
  editors = groupsCloseTab(editors, key);
  renderEditors();
  terminals = termAdopt(terminals, [pane]);
  terminalSessions.set(pane, sess);
  terminals = termFocus(terminals, pane);
  saveTerminals();
  showTerminalView();
  renderTerminalView();
  requestAnimationFrame(() => { sess.fit(); sess.focus(); });
}

// ------------------------------------------------------------------ drawing the Terminal view

function renderTerminalView() {
  if (!terminalHost) return;
  const panes = termPanes(terminals);
  const wasFocused = terminalHost.contains(document.activeElement);
  terminalHost.replaceChildren();
  terminalHost.classList.toggle("empty", !panes.length);
  if (!panes.length) {
    terminalHost.append(h("div", { class: "terminal-empty" },
      h("p", {}, session?.repo ? "No terminal is open." : "Open a project to use a terminal."),
      h("button", { class: "primary", disabled: session?.repo ? null : "", onclick: () => newTerminal() }, "New Terminal")));
    bus.emit("terminals");
    refreshViewActions("terminals");
    return;
  }
  terminalHost.classList.toggle("tabs-left", settings.get("terminal.integrated.tabs.location") === "left");
  const group = terminals.groups.find((g) => g.id === terminals.active) ?? terminals.groups[0];
  const stage = h("div", { class: "terminal-stage" });
  stage.append(buildPaneGrid(group.grid, group, []));
  terminalHost.append(stage);
  if (terminals.groups.length > 1 || panes.length > 1) terminalHost.append(terminalList());
  for (const pane of gridLeaves(group.grid)) {
    const sess = terminalSessions.get(pane);
    if (sess) { sess.fit(); }
  }
  if (wasFocused) requestAnimationFrame(() => terminalSessions.get(group.active)?.focus());
  bus.emit("terminals");
  refreshViewActions("terminals");
}

function buildPaneGrid(node, group, path) {
  if (gridIsLeaf(node)) return paneElement(node.leaf, group);
  const el = h("div", { class: `grid-split grid-${node.dir}` });
  node.children.forEach((child, i) => {
    if (i) el.append(makePaneSash(el, node.dir, group, path, i));
    const built = buildPaneGrid(child, group, [...path, i]);
    built.style.flex = `${node.sizes[i]} 1 0`;
    el.append(built);
  });
  return el;
}

function makePaneSash(split, dir, group, path, index) {
  const sash = h("div", { class: `grid-sash grid-sash-${dir}`, role: "separator", "aria-orientation": dir === "row" ? "vertical" : "horizontal" });
  sash.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    sash.setPointerCapture?.(ev.pointerId);
    document.body.classList.add("resizing");
    const kids = [...split.children].filter((c) => !c.classList.contains("grid-sash"));
    const a = kids[index - 1], b = kids[index];
    const boxA = a.getBoundingClientRect(), boxB = b.getBoundingClientRect();
    const horizontal = dir === "row";
    const start = horizontal ? boxA.left : boxA.top;
    const total = (horizontal ? boxA.width + boxB.width : boxA.height + boxB.height) || 1;
    const node = path.reduce((n, i) => n.children[i], group.grid);
    const weights = node.sizes.slice();
    const pair = weights[index - 1] + weights[index];
    const move = (e) => {
      const share = Math.min(0.9, Math.max(0.1, ((horizontal ? e.clientX : e.clientY) - start) / total));
      weights[index - 1] = pair * share;
      weights[index] = pair * (1 - share);
      a.style.flex = `${weights[index - 1]} 1 0`;
      b.style.flex = `${weights[index]} 1 0`;
      bus.emit("fit");
    };
    sash.addEventListener("pointermove", move);
    sash.addEventListener("lostpointercapture", () => {
      sash.removeEventListener("pointermove", move);
      document.body.classList.remove("resizing");
      group.grid = gridSetSizes(group.grid, path, weights);
      saveTerminals();
      bus.emit("fit");
    }, { once: true });
  });
  return sash;
}

function paneElement(pane, group) {
  let sess = terminalSessions.get(pane);
  if (!sess) {
    sess = new TerminalSession({ kind: "shell", pane, name: "shell", hints: [
      `\x1b[2mThe tools claude has: cc, make, valgrind, norminette, vim, nano, and docker on the separate daemon. The subject PDFs of this review are in $SUBJECTS_DIR.\x1b[0m`,
    ], onEnded: () => { killTerminal(pane); } });
    terminalSessions.set(pane, sess);
    queueMicrotask(() => sess.start().then(() => sess.fit()));
  }
  const active = group.active === pane;
  const el = h("div", {
    class: `terminal-pane ${active ? "active" : ""}`, "data-pane": pane,
    onmousedown: () => { if (termActivePane(terminals) !== pane) { terminals = termFocus(terminals, pane); saveTerminals(); $$(".terminal-pane", terminalHost).forEach((p) => p.classList.toggle("active", p.dataset.pane === pane)); refreshTerminalList(); } },
    oncontextmenu: (ev) => { ev.preventDefault(); terminals = termFocus(terminals, pane); showContextMenu(ev, terminalMenu(pane)); },
    // a file of the explorer dropped here is typed at the prompt, as a path from the project folder (VS Code does the same)
    ondragover: (ev) => { if ((ev.dataTransfer?.types ?? []).includes("application/x-verdict-path")) ev.preventDefault(); },
    ondrop: (ev) => {
      const path = ev.dataTransfer?.getData?.("application/x-verdict-path");
      if (!path) return;
      ev.preventDefault();
      ev.stopPropagation();
      sess.send({ t: "i", d: `${shellQuote(path)} ` });
      focusPane(pane);
    },
  }, sess.element);
  return el;
}

function terminalMenu(pane) {
  return [
    { label: "Split Terminal Right", run: () => { terminals = termFocus(terminals, pane); splitTerminal("right"); } },
    { label: "Split Terminal Down", run: () => { terminals = termFocus(terminals, pane); splitTerminal("down"); } },
    "-",
    { label: "Rename...", run: () => renameTerminal(pane) },
    { label: "Move Terminal into Editor Area", run: () => moveTerminalToEditor(pane) },
    "-",
    { label: "Clear", run: () => terminalSessions.get(pane)?.term?.clear() },
    { label: "Kill Terminal", run: () => killTerminal(pane) },
  ];
}

function terminalList() {
  const rows = [];
  for (const group of terminals.groups) {
    const leaves = gridLeaves(group.grid);
    leaves.forEach((pane, i) => {
      const activeGroup = group.id === terminals.active;
      const title = terminals.titles[pane] || "zsh";
      const label = renamingPane === pane
        ? h("input", { class: "terminal-rename", type: "text", value: title, "aria-label": "Rename terminal",
          onkeydown: (ev) => { if (ev.key === "Enter") { terminals = termRename(terminals, pane, ev.target.value); renamingPane = null; saveTerminals(); renderTerminalView(); } else if (ev.key === "Escape") { renamingPane = null; renderTerminalView(); } },
          onblur: (ev) => { if (renamingPane === pane) { terminals = termRename(terminals, pane, ev.target.value); renamingPane = null; saveTerminals(); renderTerminalView(); } } })
        : h("span", { class: "terminal-title" }, title);
      rows.push(h("div", {
        class: `terminal-row ${activeGroup && group.active === pane ? "active" : ""} ${leaves.length > 1 ? (i === 0 ? "split-first" : "split-child") : ""}`, role: "tab", "data-pane": pane,
        title: `${title} (${pane})`, onclick: () => focusPane(pane), ondblclick: () => renameTerminal(pane),
        oncontextmenu: (ev) => { ev.preventDefault(); showContextMenu(ev, terminalMenu(pane)); },
      }, icon("terminal", 14), label, iconButton("trash", "Kill Terminal", (ev) => { ev.stopPropagation(); killTerminal(pane); })));
    });
  }
  const list = h("div", { class: "terminal-list", role: "tablist" }, rows);
  setTimeout(() => $(".terminal-rename", list)?.select?.(), 0);
  return list;
}

function refreshTerminalList() {
  const old = $(".terminal-list", terminalHost);
  if (old) old.replaceWith(terminalList());
}

// The view in the panel (registered with the others in views.js)
function createTerminalView(body) {
  terminalHost = h("div", { class: "terminal-view" });
  body.append(terminalHost);
  adoptRunningShells();
  renderTerminalView();
}

function terminalViewActions() {
  const have = termPanes(terminals).length > 0;
  return [
    { icon: "plus", title: `New Terminal (${keyLabel("workbench.action.terminal.new")})`, run: () => newTerminal(), disabled: !session?.repo },
    { icon: "split-right", title: `Split Terminal (${keyLabel("workbench.action.terminal.split")})`, run: (ev) => splitTerminal(ev?.altKey ? "down" : "right"), disabled: !have },
    { icon: "trash", title: "Kill Terminal", run: () => killTerminal(), disabled: !have },
  ];
}

// A new colour theme: the terminals that are open take its colours too.
bus.on("theme", () => {
  const theme = termTheme();
  for (const sess of [...terminalSessions.values(), ...[...tabs.values()].map((t) => t.session).filter(Boolean)]) if (sess.term) sess.term.options.theme = theme;
});

bus.on("fit", () => { clearTimeout(bus.fitTimer); bus.fitTimer = setTimeout(() => { for (const sess of terminalSessions.values()) sess.fit(); tabs.get("terminal")?.session?.fit(); for (const t of tabs.values()) if (t.session) t.session.fit(); }, 30); });
bus.on("setting", (id) => {
  if (id === "terminal.integrated.tabs.location") terminalHost?.classList.toggle("tabs-left", settings.get(id) === "left");
  if (!id.startsWith("terminal.integrated.") && id !== "window.zoomLevel") return;
  for (const sess of [...terminalSessions.values(), ...[...tabs.values()].map((t) => t.session).filter(Boolean)]) {
    if (!sess.term) continue;
    sess.term.options.fontSize = settings.get("terminal.integrated.fontSize") * zoomFactor();
    sess.term.options.cursorStyle = settings.get("terminal.integrated.cursorStyle");
    sess.term.options.cursorBlink = settings.get("terminal.integrated.cursorBlinking");
    sess.term.options.scrollback = settings.get("terminal.integrated.scrollback");
    sess.fit();
  }
});
