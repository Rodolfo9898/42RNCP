"use strict";

// The views: what the side bars and the panel show. Each is registered into a container (the icons of the activity bar, the tabs of the
// panel) and can be dragged to another place (layout.js). A view builds itself once, then draws again when the data changes.

const viewTitle = (spec) => (typeof spec.title === "function" ? spec.title() : spec.title);

let treeEntries = [];            // the files and folders of the repository, as the server listed them

// ------------------------------------------------------------------ explorer: Open Editors

registerContainer({ id: "explorer", title: "Explorer", icon: "files", location: "sidebar", order: 1 });
registerView({
  id: "openEditors", container: "explorer", order: 1, title: "Open Editors", collapsed: true,
  create(body) {
    this.list = h("div", { class: "open-editors" });
    body.append(this.list);
    bus.on("editors", () => { if (viewIsVisible("openEditors")) this.refresh(); });
  },
  refresh() {
    const groups = gridLeaves(editors.grid);
    const rows = [];
    groups.forEach((gid, n) => {
      if (groups.length > 1) rows.push(h("div", { class: "open-group" }, `Group ${n + 1}`));
      for (const key of editors.groups[gid].tabs) {
        const tab = tabs.get(key);
        if (!tab) continue;
        rows.push(h("div", { class: `row open-row ${key === activeTab ? "active" : ""}`, title: tab.tooltip || tab.title, onclick: () => showTab(key) },
          h("button", { class: "icon-button open-close", title: "Close", onclick: (ev) => { ev.stopPropagation(); if (tab.closable) closeTab(key); } }, tab.closable ? icon("x", 14) : ""),
          tab.iconEl ? tab.iconEl() : null, h("span", { class: "open-title" }, tab.title), h("span", { class: "open-path" }, tab.path && tab.path.includes("/") ? tab.path.slice(0, tab.path.lastIndexOf("/")) : "")));
      }
    });
    this.list.replaceChildren(...rows);
  },
  actions: () => [{ icon: "x", title: "Close All Editors", run: () => runCommand("workbench.action.closeAllEditors") }],
});

// ------------------------------------------------------------------ explorer: the repository

// Which folders are open is remembered for each repository, like VS Code does for a workspace.
const treeKey = () => `verdict.expanded:${session?.repo?.path || ""}`;

function readExpanded() {
  const saved = store.get(treeKey(), null);
  return Array.isArray(saved) ? new Set(saved) : null;
}

function writeExpanded() {
  store.set(treeKey(), $$("#tree .row[data-dir]").filter((r) => r.getAttribute("aria-expanded") === "true").map((r) => r.dataset.dir));
}

function selectRow(row) {                       // the row the keyboard is on (not the same thing as the file open in front, which is "active")
  $$("#tree .row.selected").forEach((r) => r.classList.remove("selected"));
  row.classList.add("selected");
  row.scrollIntoView?.({ block: "nearest" });
}

function collapseAll() {
  $$("#tree .row[data-dir]").forEach((row) => row.setOpen?.(false, false));
  writeExpanded();
}

// Reads the files of the repository (for the explorer, Go to File and the breadcrumbs), and draws them if the explorer is on the page.
async function loadTree() {
  await loadIconTheme();
  treeEntries = await api(`sessions/${sid}/tree`).catch(() => []);
  drawTree();
  bus.emit("tree", treeEntries);
}

function drawTree() {
  const entries = treeEntries;
  const root = $("#tree");
  if (!root) return;
  $("#tree-hint").hidden = entries.length > 0;
  const remembered = readExpanded();             // null until a folder is opened or closed: then the top-level folders are open
  const nodes = new Map([["", h("div", { class: "children" })]]);
  const mk = (entry) => {
    const name = entry.path.split("/").pop();
    const depth = entry.path.split("/").length - 1;
    const pad = `padding-left:${8 + depth * 12}px`;
    if (entry.type === "dir") {
      const open = remembered ? remembered.has(entry.path) : depth === 0;
      const kids = h("div", { class: "children", role: "group", hidden: !open });
      nodes.set(entry.path, kids);
      const twisty = h("span", { class: "twisty" }, icon(open ? "chevron-down" : "chevron-right", 14));
      const folderIcon = fileIcon(iconFor(name, "dir", open));
      const row = h("div", { class: "row", role: "treeitem", "aria-expanded": String(open), "data-dir": entry.path, style: pad,
        oncontextmenu: (ev) => { ev.preventDefault(); selectRow(row); showContextMenu(ev, treeMenu(entry)); } });
      row.setOpen = (value, save = true) => {
        kids.hidden = !value;
        twisty.replaceChildren(icon(value ? "chevron-down" : "chevron-right", 14));
        row.setAttribute("aria-expanded", String(value));
        const src = iconFor(name, "dir", value);
        if (src && folderIcon.tagName === "IMG") folderIcon.src = src;
        if (save) writeExpanded();
      };
      row.addEventListener("click", () => { selectRow(row); row.setOpen(kids.hidden); });
      row.append(twisty, folderIcon, h("span", { class: "row-name" }, name));
      return [h("div", {}, row, kids)];
    }
    const row = h("div", { class: "row", role: "treeitem", style: pad, "data-path": entry.path, draggable: "true",
      onclick: () => { selectRow(row); row.openFile(); }, ondblclick: () => guarded(() => openFile(entry.path)),      // (not pinTab: the file may still be loading from the first click)
      oncontextmenu: (ev) => { ev.preventDefault(); selectRow(row); showContextMenu(ev, treeMenu(entry)); },
      ondragstart: (ev) => { ev.dataTransfer.setData("application/x-verdict-path", entry.path); ev.dataTransfer.setData("text/plain", entry.path); ev.dataTransfer.effectAllowed = "copyMove"; },
    }, h("span", { class: "twisty" }, ""), fileIcon(iconFor(name)), h("span", { class: "row-name" }, name));
    row.openFile = () => guarded(() => openFile(entry.path, undefined, { preview: true }));      // a single click shows it in a preview tab
    return [h("div", {}, row)];
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
  markActiveInTree();
  decorateTree();
}

function markActiveInTree() {
  $$("#tree .row").forEach((row) => row.classList.toggle("active", row.dataset.path === activeTab));
}

function treeMenu(entry) {
  const dir = entry.type === "dir";
  return [
    dir ? { label: "Expand or Collapse", run: () => $(`#tree .row[data-dir="${CSS.escape(entry.path)}"]`)?.click() } : { label: "Open", run: () => guarded(() => openFile(entry.path)) },
    ...(dir ? [] : [{ label: "Open to the Side", run: () => guarded(async () => { const g = splitGroup(editors.active, "right"); await openFile(entry.path, undefined, { group: g }); }) }]),
    "-",
    { label: "Find in Folder...", run: () => findInFiles("", dir ? `${entry.path}/` : entry.path.slice(0, Math.max(0, entry.path.lastIndexOf("/") + 1)) || "") },
    "-",
    { label: "Copy Path", run: () => copyText(entry.path, "the path") },
    { label: "Copy Relative Path", run: () => copyText(entry.path, "the relative path") },
    { label: "Select for Compare", disabled: dir, run: () => { compareSelection = entry.path; notify(`${entry.path} is selected: choose "Compare with Selected" on another file.`); } },
    { label: "Compare with Selected", disabled: dir || !compareSelection || compareSelection === entry.path, run: () => guarded(() => compareFiles(compareSelection, entry.path)) },
  ];
}

let compareSelection = null;

registerView({
  id: "files", container: "explorer", order: 2,
  title: () => (session?.repo ? (session.repo.name || session.repo.path || "Repository") : "Repository"),
  create(body) {
    body.append(
      h("div", { id: "tree", class: "tree", role: "tree", tabindex: "0", "aria-label": "Repository" }),
      h("p", { class: "hint", id: "tree-hint" }, "No repository cloned yet. Use File > Open Project."));
    wireTreeKeys($("#tree"));
    if (treeEntries.length) drawTree(); else loadTree();
  },
  refresh() { markActiveInTree(); },
  actions: () => [
    { icon: "refresh", title: "Refresh Explorer", run: () => guarded(loadTree) },
    { icon: "collapse-all", title: "Collapse Folders in Explorer", run: collapseAll },
  ],
});

const visibleRows = () => $$("#tree .row").filter((row) => !row.closest(".children[hidden]"));

function wireTreeKeys(tree) {
  tree.addEventListener("keydown", (ev) => {
    if (ev.altKey || ev.ctrlKey || ev.metaKey) return;
    const rows = visibleRows();
    if (!rows.length) return;
    const at = rows.findIndex((r) => r.classList.contains("selected"));
    const row = rows[at];
    const go = (i) => { ev.preventDefault(); selectRow(rows[Math.max(0, Math.min(rows.length - 1, i))]); };
    if (ev.key === "ArrowDown") go(at + 1);
    else if (ev.key === "ArrowUp") go(at < 0 ? 0 : at - 1);
    else if (ev.key === "Home") go(0);
    else if (ev.key === "End") go(rows.length - 1);
    else if (ev.key === "ArrowRight" && row?.dataset.dir !== undefined) {
      ev.preventDefault();
      if (row.getAttribute("aria-expanded") === "false") row.setOpen(true);
      else go(at + 1);                                                       // already open: into its first entry
    } else if (ev.key === "ArrowLeft" && row) {
      ev.preventDefault();
      if (row.dataset.dir !== undefined && row.getAttribute("aria-expanded") === "true") row.setOpen(false);
      else {                                                                 // otherwise: up to the folder that holds it
        const path = row.dataset.dir ?? row.dataset.path;
        const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : null;
        const up = parent === null ? null : rows.find((r) => r.dataset.dir === parent);
        if (up) selectRow(up);
      }
    } else if ((ev.key === "Enter" || ev.key === " ") && row) {
      ev.preventDefault();
      if (row.dataset.dir !== undefined) row.setOpen(row.getAttribute("aria-expanded") !== "true");
      else guarded(() => openFile(row.dataset.path));                        // Enter keeps the file open (a click only previews it)
    } else if (ev.key === "F2" || ev.key === "Delete") ev.preventDefault();      // (the files are read-only here)
  });
  tree.addEventListener("focus", () => {
    if (!tree.querySelector(".row.selected")) { const row = tree.querySelector(".row.active") || visibleRows()[0]; if (row) selectRow(row); }
  });
}

function revealInExplorer(path) {
  setLayout(layoutRevealView(layout, "files"));
  const parts = path.split("/");
  for (let i = 1; i < parts.length; i++) $(`#tree .row[data-dir="${CSS.escape(parts.slice(0, i).join("/"))}"]`)?.setOpen?.(true);
  const row = $(`#tree .row[data-path="${CSS.escape(path)}"], #tree .row[data-dir="${CSS.escape(path)}"]`);
  if (row) { selectRow(row); $("#tree").focus({ preventScroll: true }); }
}

// ------------------------------------------------------------------ explorer: Outline

registerView({
  id: "outline", container: "explorer", order: 3, title: "Outline", collapsed: true,
  create(body) {
    this.list = h("div", { class: "outline" });
    body.append(this.list);
    const redo = () => { if (viewIsVisible("outline")) this.refresh(); };
    bus.on("tab:active", redo);
    bus.on("cursor", redo);
  },
  refresh() {
    const tab = tabs.get(activeTab);
    const symbols = outlineOfTab(tab);
    const here = tab?.cursor?.line ?? 0;
    const current = symbols.filter((s) => s.line <= here).pop();
    this.list.replaceChildren(...(symbols.length ? symbols.map((s) => h("div", {
      class: `row outline-row ${s === current ? "active" : ""}`, style: `padding-left:${12 + s.depth * 12}px`, title: `${s.kind} ${s.name} (line ${s.line})`,
      onclick: () => revealLine(tab.key, s.line),
    }, h("span", { class: `symbol symbol-${s.kind}` }, { function: "ƒ", macro: "#", struct: "S", union: "U", enum: "E", class: "C", heading: "H", target: "▸", variable: "V", namespace: "N" }[s.kind] ?? "·"), h("span", { class: "row-name" }, s.name)))
      : [h("p", { class: "hint" }, tab?.text ? "The active editor cannot provide outline information." : "No editor with a file is active.")]));
  },
});

// ------------------------------------------------------------------ search

registerContainer({ id: "search", title: "Search", icon: "search", location: "sidebar", order: 2 });
const searchState = { query: "", caseSensitive: false, word: false, regex: false, include: "", exclude: "", detailsOpen: false, results: null, error: "", running: false, token: 0, collapsed: new Set() };

registerView({
  id: "search", container: "search", title: "Search",
  create(body) {
    const input = h("input", { type: "text", class: "search-input", placeholder: "Search", "aria-label": "Search", spellcheck: "false", autocomplete: "off" });
    const include = h("input", { type: "text", placeholder: "e.g. *.c, src/**", "aria-label": "files to include", spellcheck: "false" });
    const exclude = h("input", { type: "text", placeholder: "e.g. libs/, *.o", "aria-label": "files to exclude", spellcheck: "false" });
    const toggle = (label, title, key) => h("button", { class: "find-toggle", title, "aria-label": title, "aria-pressed": "false", onclick: (ev) => { searchState[key] = !searchState[key]; ev.currentTarget.classList.toggle("on", searchState[key]); ev.currentTarget.setAttribute("aria-pressed", String(searchState[key])); runSearch(); } }, label);
    const details = h("div", { class: "search-details", hidden: true }, h("label", {}, "files to include"), include, h("label", {}, "files to exclude"), exclude);
    const summary = h("div", { class: "search-summary" });
    const results = h("div", { class: "search-results", role: "tree" });
    const root = h("div", { class: "search-view" },
      h("div", { class: "search-box" },
        h("button", { class: "icon-button search-details-toggle", title: "Toggle Search Details", "aria-label": "Toggle Search Details", onclick: () => { searchState.detailsOpen = !searchState.detailsOpen; details.hidden = !searchState.detailsOpen; } }, icon("more", 16)),
        input, toggle("Aa", "Match Case (Alt+C)", "caseSensitive"), toggle("ab", "Match Whole Word (Alt+W)", "word"), toggle(".*", "Use Regular Expression (Alt+R)", "regex")),
      details, summary, results);
    input.addEventListener("input", () => { searchState.query = input.value; clearTimeout(this.timer); this.timer = setTimeout(runSearch, 350); });
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); clearTimeout(this.timer); runSearch(); }
      else if (ev.key === "Escape") { input.value = ""; searchState.query = ""; searchState.results = null; renderSearch(); }
      else if (ev.altKey && ev.code === "KeyC") { ev.preventDefault(); $$(".find-toggle", root)[0].click(); }
      else if (ev.altKey && ev.code === "KeyW") { ev.preventDefault(); $$(".find-toggle", root)[1].click(); }
      else if (ev.altKey && ev.code === "KeyR") { ev.preventDefault(); $$(".find-toggle", root)[2].click(); }
    });
    for (const [el, key] of [[include, "include"], [exclude, "exclude"]]) {
      el.addEventListener("input", () => { searchState[key] = el.value; clearTimeout(this.timer); this.timer = setTimeout(runSearch, 450); });
      el.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); runSearch(); } });
    }
    Object.assign(this, { input, include, exclude, details, summary, results });
    body.append(root);
  },
  refresh() { renderSearch(); },
  actions: () => [
    { icon: "refresh", title: "Refresh", run: () => runSearch(), disabled: !searchState.query },
    { icon: "x", title: "Clear Search Results", run: () => { searchState.results = null; searchState.query = ""; const v = viewSpecs.get("search"); if (v.input) v.input.value = ""; renderSearch(); } },
    { icon: "collapse-all", title: "Collapse All", run: () => { for (const f of searchState.results?.files ?? []) searchState.collapsed.add(f.path); renderSearch(); } },
  ],
});

async function runSearch() {
  const spec = viewSpecs.get("search");
  const token = ++searchState.token;
  if (!searchState.query.trim() || !session?.repo) { searchState.results = null; searchState.error = ""; renderSearch(); return; }
  searchState.running = true;
  renderSearch();
  const params = new URLSearchParams({ q: searchState.query, case: searchState.caseSensitive, word: searchState.word, regex: searchState.regex, include: searchState.include, exclude: searchState.exclude });
  try {
    const answer = await api(`sessions/${sid}/search?${params}`);
    if (token !== searchState.token) return;                    // a newer search was started
    searchState.results = answer.error ? null : answer;
    searchState.error = answer.error;
  } catch (err) {
    if (token !== searchState.token) return;
    searchState.results = null;
    searchState.error = err.message;
  } finally {
    if (token === searchState.token) { searchState.running = false; renderSearch(); }
  }
}

function renderSearch() {
  const spec = viewSpecs.get("search");
  if (!spec.results) return;
  const { results, summary } = spec;
  const r = searchState.results;
  summary.textContent = searchState.running ? "Searching…" : searchState.error ? searchState.error
    : !searchState.query.trim() ? "" : !r ? "" : r.total ? `${r.total} result${r.total === 1 ? "" : "s"} in ${r.files.length} file${r.files.length === 1 ? "" : "s"}${r.truncated ? " (more were left out)" : ""}`
    : "No results found.";
  summary.classList.toggle("error", !!searchState.error);
  if (!r) { results.replaceChildren(); return; }
  results.replaceChildren(...r.files.map((f) => {
    const name = f.path.split("/").pop(), dir = f.path.includes("/") ? f.path.slice(0, f.path.lastIndexOf("/")) : "";
    const closed = searchState.collapsed.has(f.path);
    const head = h("div", { class: "row search-file", role: "treeitem", "aria-expanded": String(!closed), title: f.path,
      onclick: () => { closed ? searchState.collapsed.delete(f.path) : searchState.collapsed.add(f.path); renderSearch(); },
      ondblclick: () => guarded(() => openFile(f.path)) },
    h("span", { class: "twisty" }, icon(closed ? "chevron-right" : "chevron-down", 14)), fileIcon(iconFor(name)), h("span", { class: "row-name" }, name), h("span", { class: "row-dir" }, dir),
    h("span", { class: "count" }, String(f.matches.length)));
    const rows = closed ? [] : f.matches.map((m) => {
      const text = m.preview, at = m.col - m.preview_start;
      return h("div", { class: "row search-match", role: "treeitem", title: `${f.path}:${m.line}`, onclick: () => guarded(() => openFile(f.path, m.line, { preview: true, column: m.col })) },
        h("span", { class: "match-text" }, at >= 0 && at + m.length <= text.length
          ? [text.slice(Math.max(0, at - 20), at).replace(/^\s+/, ""), h("mark", {}, text.slice(at, at + m.length)), text.slice(at + m.length, at + m.length + 80)]
          : text.slice(0, 100)));
    });
    return h("div", { class: "search-group" }, head, ...rows);
  }));
}

// Find in Files: show the Search view with the text (and the folder to look in) filled in.
function findInFiles(seed = "", include = "") {
  setLayout(layoutRevealView(layout, "search"));
  const spec = viewSpecs.get("search");
  const selected = seed || document.getSelection()?.toString() || "";
  requestAnimationFrame(() => {
    if (!spec.input) return;
    if (selected && !selected.includes("\n") && selected.length < 200) { spec.input.value = selected; searchState.query = selected; }
    spec.include.value = include;
    searchState.include = include;
    searchState.detailsOpen = searchState.detailsOpen || !!include;
    spec.details.hidden = !searchState.detailsOpen;
    spec.input.focus();
    spec.input.select();
    if (searchState.query) runSearch();
  });
}

// ------------------------------------------------------------------ subjects

registerContainer({ id: "subjects", title: "Subjects", icon: "book", location: "sidebar", order: 4, badge: () => session?.subjects?.length || 0 });
const TRACK_LABEL = { "common-core": "Common Core", "post-common-core": "Post Common Core", rncp: "RNCP" };

registerView({
  id: "subjects", container: "subjects", title: "Subjects",
  create(body) {
    this.list = h("ul", { class: "list" });
    this.hint = h("p", { class: "hint" }, "Drop PDFs here, or use Upload / Library.");
    body.append(this.list, this.hint);
  },
  refresh() {
    if (!session) return;
    // The whole row opens the PDF (icon, name and the grey details), not just the name text.
    const open = (s) => () => guarded(() => openSubject(s.name));
    this.list.replaceChildren(...session.subjects.map((s) => s.kind === "norm"
      ? h("li", { class: "open", title: "Click to open the Norm. C code was detected: norminette runs, and the Norm rules it cannot check go to the manual review", onclick: open(s) },
        fileIcon(iconFor(s.name)), h("span", { class: "name link" }, s.name), h("span", { class: "meta" }, `Norm · auto (C) · ${s.rules.length} rules`))
      : h("li", { class: "open", title: `${s.rules.length} rules extracted. Click to open the PDF.`, onclick: open(s) },
        fileIcon(iconFor(s.name)), h("span", { class: "name link" }, s.name),
        h("span", { class: "meta" }, [TRACK_LABEL[s.track], `${s.rules.length} rules`].filter(Boolean).join(" · ")),
        h("button", { class: "x", title: "Remove", onclick: (ev) => {
          ev.stopPropagation();                                   // removing a subject must not also open it
          guarded(async () => {
            setSession(await api(`sessions/${sid}/subjects/${encodeURIComponent(s.name)}`, { method: "DELETE" }));
            if (tabs.has(`pdf:${s.name}`)) closeTab(`pdf:${s.name}`);
          });
        } }, icon("x", 14)))));
    this.hint.hidden = session.subjects.length > 0;
  },
  actions: () => [
    { icon: "book", title: "Add Subjects from the Library...", run: () => runCommand("verdict.addSubjectsFromLibrary") },
    { icon: "upload", title: "Upload Subject PDFs...", run: () => runCommand("verdict.uploadSubjects") },
  ],
});

// ------------------------------------------------------------------ run: the checks

registerContainer({ id: "run", title: "Run", icon: "play", location: "sidebar", order: 5 });
registerView({
  id: "run", container: "run", title: "Run",
  create(body) {
    const button = (label, command, primary = false) => h("button", { class: primary ? "primary wide" : "wide", "data-command": command, onclick: () => runCommand(command) }, label);
    this.status = h("div", { class: "run-status" });
    this.root = h("div", { class: "run-view" },
      h("p", { class: "run-lead" }, "Start again from nothing: close claude, delete the old verdict.md, git pull the project, then run every check."),
      button("Run Checks", "verdict.run", true),
      this.status,
      button("Open Project…", "workbench.action.files.openProject"),
      button("Check the Environment", "verdict.environment"));
    body.append(this.root);
  },
  refresh() {
    if (!session) return;
    const s = session.summary;
    const run = $('[data-command="verdict.run"]', this.root);
    run.disabled = busy() || !session.repo || !session.subjects.length;
    run.textContent = session.state === "running" ? "Running…" : "Run Checks";
    run.title = !session.repo ? "Open a project first" : !session.subjects.length ? "Add at least one subject PDF first" : `Run Checks (${keyLabel("verdict.run")})`;
    const counts = Object.fromEntries(ORDER.map((k) => [k, session.results.filter((r) => shownStatus(r) === k).length]));
    this.status.replaceChildren(
      h("div", { class: `verdict-badge small ${s.overall === "FAIL" ? "FAIL" : s.overall === "PASS" ? "PASS" : s.overall === "NOT RUN" ? "none" : "review"}` }, s.overall),
      session.results.length ? h("div", { class: "run-counts" }, ORDER.filter((k) => counts[k]).map((k) => h("span", { class: `st-${k}` }, `${ICON[k]} ${counts[k]} ${SHORT[k].toLowerCase()}`))) : null,
      session.message ? h("p", { class: "hint" }, session.message) : null);
    $('[data-command="workbench.action.files.openProject"]', this.root).disabled = busy();
  },
});

registerContainer({ id: "review", title: "Review", icon: "chat", location: "sidebar", order: 6 });
registerView({
  id: "review", container: "review", title: "Review",
  create(body) {
    const item = (label, command, note) => h("div", { class: "review-item" }, h("button", { class: "wide", "data-command": command, onclick: () => runCommand(command) }, label), h("p", { class: "hint" }, note));
    this.root = h("div", { class: "run-view" },
      item("Open Claude", "verdict.openClaude", "claude in a terminal on this project: it reads the code, asks before running anything, and writes a report that is merged into verdict.md."),
      item("AI Review", "verdict.aiReview", "Asks claude (or another model) to describe the repository and weigh the manual-review items. It has the final say once merged."),
      item("Fix Prompt", "verdict.fixPrompt", "Writes a prompt that asks an AI to fix everything the review found."));
    body.append(this.root);
  },
  refresh() {
    if (!session) return;
    const claude = $('[data-command="verdict.openClaude"]', this.root);
    claude.disabled = !session.repo;
    const ai = $('[data-command="verdict.aiReview"]', this.root);
    ai.disabled = busy() || !session.results.length || !llm.configured;
    ai.textContent = session.ai.state === "running" ? "AI working…" : "AI Review";
    ai.title = !llm.configured ? "Not configured: set ANTHROPIC_API_KEY, or LLM_BASE_URL + LLM_API_KEY + LLM_MODEL, in .env (see the README)" : !session.results.length ? "Run the checks first" : "Ask an AI model to describe the repository and weigh the manual-review items";
    const fix = $('[data-command="verdict.fixPrompt"]', this.root);
    fix.disabled = busy() || !session.results.length;
    fix.title = session.results.length ? "Write a prompt that asks an AI to fix everything the review found" : "Run the checks first";
  },
});

// ------------------------------------------------------------------ the panel: problems, output, terminal, improvements, rules

registerContainer({
  id: "problems", title: "Problems", location: "panel", order: 1,
  badge: () => (session?.results ? session.results.filter((r) => ["fail", "warn"].includes(shownStatus(r))).length : 0),
});
registerView({
  id: "checklist", container: "problems", title: "Problems",
  create(body) {
    this.bar = h("div", { class: "filters" });
    this.list = h("div", { class: "problems-list" });
    body.append(this.bar, this.list);
  },
  refresh() {
    if (!session) return;
    const counts = Object.fromEntries(ORDER.map((k) => [k, session.results.filter((r) => shownStatus(r) === k).length]));
    this.bar.replaceChildren(...ORDER.map((k) => h("button", {
      class: `chip ${shown.has(k) ? "on" : ""}`, title: `Toggle ${TITLES[k].toLowerCase()}`,
      onclick: () => { shown.has(k) ? shown.delete(k) : shown.add(k); this.refresh(); },
    }, `${ICON[k]} ${counts[k]}`)));
    const keep = this.list.scrollTop;
    this.list.replaceChildren(renderChecks());
    this.list.scrollTop = keep;
  },
});

registerContainer({ id: "output", title: "Output", location: "panel", order: 2 });
const outputLog = { channels: { Checks: [], "AI review": [], Project: [] }, channel: "Checks" };

function logOutput(channel, text) {
  const lines = outputLog.channels[channel];
  if (!lines || !text) return;
  lines.push({ at: new Date(), text });
  if (lines.length > 500) lines.shift();
  bus.emit("output", channel);
}

registerView({
  id: "log", container: "output", title: "Output",
  create(body) {
    const select = h("select", { class: "output-channel", "aria-label": "Output channel", onchange: (ev) => { outputLog.channel = ev.target.value; this.refresh(); } },
      Object.keys(outputLog.channels).map((name) => h("option", { value: name }, name)));
    this.lines = h("pre", { class: "output-lines" });
    body.append(h("div", { class: "output-bar" }, select), this.lines);
    this.select = select;
    bus.on("output", (channel) => { if (channel === outputLog.channel && viewIsVisible("log")) this.refresh(); });
  },
  refresh() {
    this.select.value = outputLog.channel;
    const stamp = (d) => d.toTimeString().slice(0, 8);
    const pinned = this.lines.scrollTop + this.lines.clientHeight >= this.lines.scrollHeight - 8;
    this.lines.textContent = outputLog.channels[outputLog.channel].map((l) => `[${stamp(l.at)}] ${l.text}`).join("\n");
    if (pinned) this.lines.scrollTop = this.lines.scrollHeight;
  },
  actions: () => [{ icon: "trash", title: "Clear Output", run: () => { outputLog.channels[outputLog.channel].length = 0; viewSpecs.get("log").refresh?.(); } }],
});

// What happened, as lines in the Output view: the state of the run, the pull, the AI's steps.
let outputSeen = { state: null, message: null, aiSteps: 0, aiState: null, repo: null };
function trackOutput() {
  if (!session) return;
  const s = outputSeen;
  if (session.state !== s.state) { logOutput("Checks", { idle: "Ready.", cloning: "Cloning the repository…", running: "Running the checks…", done: "The checks are done.", error: `The run failed: ${session.message}` }[session.state] ?? session.state); s.state = session.state; }
  if (session.message && session.message !== s.message) { logOutput(session.state === "cloning" ? "Project" : "Checks", session.message); s.message = session.message; }
  const repo = session.repo ? `${session.repo.path || session.repo.url} @ ${session.repo.commit}` : null;
  if (repo && repo !== s.repo) { logOutput("Project", `Project: ${repo}`); s.repo = repo; }
  const steps = session.ai.progress ?? [];
  if (steps.length < s.aiSteps) s.aiSteps = 0;                      // a new review starts its log again
  for (const step of steps.slice(s.aiSteps)) logOutput("AI review", step.text);
  s.aiSteps = steps.length;
  if (session.ai.state !== s.aiState) { if (s.aiState !== null && session.ai.state !== "idle") logOutput("AI review", `AI review: ${session.ai.state}${session.ai.message ? ` (${session.ai.message})` : ""}`); s.aiState = session.ai.state; }
}

registerContainer({ id: "terminal", title: "Terminal", location: "panel", order: 3 });
registerView({
  id: "terminals", container: "terminal", title: "Terminal",
  create: (body) => createTerminalView(body),
  refresh() { /* the terminals draw themselves when something happens to them: a new data of the review does not touch them */ },
  actions: () => terminalViewActions(),
});

registerContainer({ id: "improvements", title: "Improvements", location: "panel", order: 4, badge: () => session?.improvements?.length || 0 });
registerView({
  id: "improvementsList", container: "improvements", title: "Improvements",
  create(body) { this.host = h("div", { class: "scroll-host" }); body.append(this.host); },
  refresh() { if (session) this.host.replaceChildren(renderImprovements()); },
});

registerContainer({ id: "rules", title: "Subject Rules", location: "panel", order: 5 });
registerView({
  id: "rulesList", container: "rules", title: "Subject Rules",
  create(body) { this.host = h("div", { class: "scroll-host" }); body.append(this.host); },
  refresh() { if (session) this.host.replaceChildren(renderRules()); },
});
