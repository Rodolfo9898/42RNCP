"use strict";

// What makes this page behave like VS Code: keyboard shortcuts, the quick open / command palette, context menus, keyboard navigation
// of the explorer, and the tabs you had open coming back after a reload. The logic that needs no page (fuzzy matching, key matching,
// which tabs a bulk close touches, tab order) is in lib.js, where Node tests it. Everything shown comes from untrusted input (file
// names, PDFs): DOM is built with textContent only, never innerHTML.

const isSession = (key) => key === "terminal" || key === "shell";      // claude and the shell are conversations, not documents
const modalOpen = () => !$("#modal").hidden;

// ------------------------------------------------------------------ context menu

let menuCleanup = null;

function closeMenu() {
  document.getElementById("ctxmenu")?.remove();
  if (menuCleanup) { menuCleanup(); menuCleanup = null; }
}

function showMenu(x, y, items) {
  closeMenu();
  const rows = items.map((item) => item === "-" ? h("div", { class: "sep", role: "separator" })
    : h("div", { class: `mi ${item.disabled ? "disabled" : ""}`, role: "menuitem", tabindex: "-1", "aria-disabled": item.disabled ? "true" : null,
      onclick: () => { closeMenu(); if (!item.disabled) item.run(); } }, item.label));
  const menu = h("div", { id: "ctxmenu", role: "menu", tabindex: "-1" }, rows);
  document.body.append(menu);
  const box = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(0, Math.min(x, window.innerWidth - box.width - 4))}px`;       // (never partly off the page)
  menu.style.top = `${Math.max(0, Math.min(y, window.innerHeight - box.height - 4))}px`;
  const usable = rows.filter((r) => r.getAttribute("role") === "menuitem" && !r.classList.contains("disabled"));
  let at = -1;
  const mark = (i) => { at = (i + usable.length) % usable.length; usable.forEach((r, n) => r.classList.toggle("focus", n === at)); };
  const onKey = (ev) => {
    if (ev.key === "Escape") { ev.preventDefault(); closeMenu(); }
    else if (ev.key === "ArrowDown" && usable.length) { ev.preventDefault(); mark(at + 1); }
    else if (ev.key === "ArrowUp" && usable.length) { ev.preventDefault(); mark(at < 0 ? -1 : at - 1); }
    else if (ev.key === "Enter" && at >= 0) { ev.preventDefault(); usable[at].click(); }
  };
  const onOutside = (ev) => { if (!menu.contains(ev.target)) closeMenu(); };
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("mousedown", onOutside, true);
  window.addEventListener("blur", closeMenu);
  window.addEventListener("resize", closeMenu);
  menuCleanup = () => {
    document.removeEventListener("keydown", onKey, true);
    document.removeEventListener("mousedown", onOutside, true);
    window.removeEventListener("blur", closeMenu);
    window.removeEventListener("resize", closeMenu);
  };
}

// (navigator.clipboard only exists on https and on localhost: reached by another address, the page cannot copy)
const copyText = (text, what) => Promise.resolve().then(() => navigator.clipboard.writeText(text)).then(() => toast(`Copied ${what}.`, true)).catch(() => toast("Could not copy: the browser does not allow it on this address."));

// ------------------------------------------------------------------ tabs: the menu, bulk closing, going to the next one

const tabEntries = () => [...tabs].map(([key, t]) => ({ key, closable: t.closable, session: isSession(key) }));

function closeTabs(mode, key) {
  for (const k of tabsToClose(tabEntries(), mode, key)) closeTab(k);
}

function stepTab(by) {
  const keys = [...tabs.keys()];
  if (keys.length) showTab(keys[(keys.indexOf(activeTab) + by + keys.length) % keys.length]);
}

function tabMenu(ev, key) {                       // (called by renderTabs on a right click)
  const tab = tabs.get(key);
  const others = tabsToClose(tabEntries(), "others", key).length, right = tabsToClose(tabEntries(), "right", key).length;
  showMenu(ev.clientX, ev.clientY, [
    { label: "Close", disabled: !tab.closable, run: () => closeTab(key) },
    { label: "Close Others", disabled: !others, run: () => closeTabs("others", key) },
    { label: "Close to the Right", disabled: !right, run: () => closeTabs("right", key) },
    { label: "Close All", disabled: !tabsToClose(tabEntries(), "all", key).length, run: () => closeTabs("all", key) },
    "-",
    ...(tab.preview ? [{ label: "Keep Open", run: () => pinTab(key) }] : []),
    { label: "Copy Path", disabled: !tab.repoFile, run: () => copyText(key, "the path") },
  ]);
}

// ------------------------------------------------------------------ quick open and the command palette

// A command that is just a button of the top bar: when that button is switched off (no project yet, something running) say so.
const press = (id) => () => {
  const button = document.getElementById(id);
  if (button && !button.disabled) button.click();
  else toast(`${button ? button.textContent.trim() : "That"} is not available right now (open a project first, or wait for what is running).`);
};
const showPanelTab = (name) => () => { document.querySelector(`#panel-tabs [data-tab="${name}"]`)?.click(); };

// keys: the shortcut (lib.js writes them the way each platform does); also: more ways to the same command
const COMMANDS = [
  { id: "quickOpen", title: "File: Go to File…", keys: "mod+p", run: () => openPalette("") },
  { id: "palette", title: "View: Show All Commands", keys: "mod+shift+p", also: ["f1"], run: () => openPalette(">") },
  { id: "sidebar", title: "View: Toggle Sidebar", keys: "mod+b", run: () => toggleSidebar() },
  { id: "panel", title: "View: Toggle Panel", keys: "mod+j", run: () => togglePanel() },
  { id: "explorer", title: "View: Focus Explorer", keys: "mod+shift+e", run: () => focusExplorer() },
  { id: "resetLayout", title: "View: Reset Layout", run: () => resetLayout() },
  { id: "checklist", title: "View: Show Checklist", run: showPanelTab("checks") },
  { id: "improvements", title: "View: Show Improvements", run: showPanelTab("improvements") },
  { id: "rules", title: "View: Show Subject Rules", run: showPanelTab("rules") },
  { id: "shell", title: "Terminal: Open Shell", keys: "ctrl+`", run: press("btn-shell") },
  { id: "claude", title: "Terminal: Open Claude", run: press("btn-terminal") },
  { id: "run", title: "Checks: Run Checks", run: press("btn-run") },
  { id: "review", title: "Review: Ask for an AI Review", run: press("btn-ai") },
  { id: "fix", title: "Review: Write a Fix Prompt", run: press("btn-fix") },
  { id: "environment", title: "Environment: Check the Environment", run: press("btn-env") },
  { id: "project", title: "Project: Open Project…", run: press("btn-clone") },
  { id: "library", title: "Subjects: Pick from the Library…", run: press("btn-library") },
  { id: "upload", title: "Subjects: Upload PDFs…", run: press("btn-upload") },
  { id: "overview", title: "Verdict: Show the Verdict", run: () => showTab("overview") },
  { id: "download", title: "Verdict: Download verdict.md", run: () => { if (sid) window.location.href = `/api/sessions/${sid}/verdict.md?download=true`; } },
  { id: "closeTab", title: "Tabs: Close Tab", keys: "alt+w", run: () => { if (tabs.get(activeTab)?.closable) closeTab(activeTab); } },
  { id: "closeOthers", title: "Tabs: Close Other Tabs", run: () => closeTabs("others", activeTab) },
  { id: "closeRight", title: "Tabs: Close Tabs to the Right", run: () => closeTabs("right", activeTab) },
  { id: "closeAll", title: "Tabs: Close All Tabs", run: () => closeTabs("all", activeTab) },
  { id: "nextTab", title: "Tabs: Next Tab", run: () => stepTab(1) },
  { id: "previousTab", title: "Tabs: Previous Tab", run: () => stepTab(-1) },
];

// The browser owns Cmd/Ctrl+W, T, N and Ctrl+Tab: no page can take them, so "Close Tab" is Alt+W here.

let palette = null;       // { root, input, list }
let paletteItems = [];
let paletteAt = 0;
let paletteFiles = null;  // the files of the repository, read when the palette opens
let paletteFocus = null;  // what had the focus before, to give it back

const baseName = (path) => path.slice(path.lastIndexOf("/") + 1);

// A label with the matched characters in bold. `offset`: where this label starts inside the string that was searched.
function marked(text, positions, offset = 0) {
  const nodes = [];
  let plain = "";
  for (let i = 0; i < text.length; i++) {                              // (the positions are indexes into the string, as fuzzyMatch counts them)
    if (positions.includes(i + offset)) { if (plain) nodes.push(plain); plain = ""; nodes.push(h("b", { class: "hl" }, text[i])); }
    else plain += text[i];
  }
  return plain ? [...nodes, plain] : nodes;
}

function commandItems() {
  return COMMANDS.map((c, order) => ({ search: c.title, label: c.title, key: c.keys ? showKey(c.keys, IS_MAC) : "", order, run: c.run }));
}

function fileItems() {
  const open = [...tabHistory].reverse().filter((k) => tabs.has(k) && !isSession(k) && k !== "overview");
  const items = [];
  (paletteFiles || []).forEach((path, order) => {
    const name = baseName(path), dir = path.slice(0, path.length - name.length - 1);
    items.push({ search: path, label: name, detail: dir, detailIsPath: true, offset: path.length - name.length, order: 1000 + order, boost: open.includes(path) ? 40 - open.indexOf(path) : 0,
      run: () => openFile(path) });
  });
  for (const s of session.subjects) {
    items.push({ search: s.name, label: s.name, detail: "subject PDF", offset: 0, order: 500, boost: open.includes(`pdf:${s.name}`) ? 40 : 0, run: () => openSubject(s.name) });
  }
  return items;
}

function paletteRender() {
  const { list } = palette;
  if (!paletteItems.length) { list.replaceChildren(h("div", { class: "palette-empty" }, "No matching results")); return; }
  list.replaceChildren(...paletteItems.map((item, i) => h("div", {
    class: `palette-item ${i === paletteAt ? "selected" : ""}`, role: "option", "aria-selected": String(i === paletteAt),
    onmousemove: () => { if (paletteAt !== i) { paletteAt = i; paletteMarkSelected(); } },
    onclick: () => paletteAccept(i),
  }, h("span", { class: "pi-label" }, ...marked(item.label, item.positions, item.offset || 0)),
  item.detail ? h("span", { class: "pi-detail" }, ...(item.detailIsPath ? marked(item.detail, item.positions, 0) : [item.detail])) : null,
  item.key ? h("span", { class: "pi-key" }, item.key) : null)));
}

function paletteMarkSelected() {
  [...palette.list.children].forEach((el, i) => { el.classList.toggle("selected", i === paletteAt); el.setAttribute("aria-selected", String(i === paletteAt)); });
  palette.list.children[paletteAt]?.scrollIntoView({ block: "nearest" });
}

function paletteRefresh() {
  const text = palette.input.value;
  const commands = text.startsWith(">");                          // as in VS Code: a ">" turns quick open into the command palette
  const query = commands ? text.slice(1) : text;
  const scored = [];
  for (const item of commands ? commandItems() : fileItems()) {
    const match = fuzzyMatch(query, item.search);
    if (!match) continue;
    // positions are indexes into `search`; the detail (the folder) is a prefix of it, the label the rest
    scored.push({ ...item, score: match.score + (item.boost || 0), positions: match.positions });
  }
  scored.sort((a, b) => b.score - a.score || a.order - b.order || a.search.length - b.search.length);
  paletteItems = scored.slice(0, 60);
  paletteAt = 0;
  palette.input.placeholder = commands ? "Type the name of a command" : "Go to file… (type > for commands)";
  paletteRender();
}

function paletteAccept(index) {
  const item = paletteItems[index];
  if (!item) return;
  closePalette();
  guarded(async () => { await item.run(); });
}

function closePalette() {
  if (!palette || palette.root.hidden) return;
  palette.root.hidden = true;
  const back = paletteFocus;
  paletteFocus = null;
  palette.input.blur();                                                  // (a hidden box must not keep the keyboard)
  if (back && document.contains(back)) back.focus();
}

function paletteOpen() { return !!palette && !palette.root.hidden; }

async function openPalette(prefill) {
  closeMenu();
  if (!palette) {
    const input = h("input", { type: "text", spellcheck: "false", autocomplete: "off", "aria-label": "Quick open" });
    const list = h("div", { class: "palette-list", role: "listbox" });
    const root = h("div", { id: "palette", hidden: true }, h("div", { class: "palette-box" }, input, list));
    root.addEventListener("mousedown", (ev) => { if (ev.target === root) closePalette(); });
    input.addEventListener("input", paletteRefresh);
    input.addEventListener("blur", closePalette);                        // clicking anywhere else closes it, as in VS Code
    list.addEventListener("mousedown", (ev) => ev.preventDefault());      // (but not a click on one of its items: that must not take the focus first)
    input.addEventListener("keydown", (ev) => {
      const last = paletteItems.length - 1;
      if (ev.key === "ArrowDown") { ev.preventDefault(); paletteAt = paletteAt >= last ? 0 : paletteAt + 1; paletteMarkSelected(); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); paletteAt = paletteAt <= 0 ? last : paletteAt - 1; paletteMarkSelected(); }
      else if (ev.key === "PageDown") { ev.preventDefault(); paletteAt = Math.min(last, paletteAt + 8); paletteMarkSelected(); }
      else if (ev.key === "PageUp") { ev.preventDefault(); paletteAt = Math.max(0, paletteAt - 8); paletteMarkSelected(); }
      else if (ev.key === "Enter") { ev.preventDefault(); paletteAccept(paletteAt); }
      else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closePalette(); }
      else if (ev.key === "Tab") ev.preventDefault();                  // (the focus stays in the box)
    });
    document.body.append(root);
    palette = { root, input, list };
  }
  if (!paletteOpen()) paletteFocus = document.activeElement;
  palette.root.hidden = false;
  palette.input.value = prefill;
  palette.input.focus();
  paletteFiles = null;
  paletteRefresh();                                                      // commands and tabs at once,
  if (session.repo) {                                                    // the files of the repository as soon as they are read
    const entries = await api(`sessions/${sid}/tree`).catch(() => []);
    paletteFiles = entries.filter((e) => e.type === "file").map((e) => e.path).sort((a, b) => a.localeCompare(b));
    if (paletteOpen()) { const keepAt = paletteAt; paletteRefresh(); paletteAt = Math.min(keepAt, Math.max(0, paletteItems.length - 1)); paletteMarkSelected(); }
  }
}

// ------------------------------------------------------------------ the explorer from the keyboard

const visibleRows = () => [...document.querySelectorAll("#tree .row")].filter((row) => !row.closest(".children[hidden]"));

function focusExplorer() {
  if (layout.sideHidden) toggleSidebar();
  const tree = $("#tree");
  tree.focus();
  if (!tree.querySelector(".row.selected")) {
    const row = tree.querySelector(`.row.active`) || visibleRows()[0];
    if (row) selectRow(row);
  }
}

$("#tree").addEventListener("keydown", (ev) => {
  if (ev.altKey || ev.ctrlKey || ev.metaKey) return;
  const rows = visibleRows();
  if (!rows.length) return;
  let at = rows.findIndex((r) => r.classList.contains("selected"));
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
  }
});
$("#tree").addEventListener("focus", () => {
  if (!$("#tree").querySelector(".row.selected")) { const row = $("#tree").querySelector(".row.active") || visibleRows()[0]; if (row) selectRow(row); }
});
$("#tree").addEventListener("contextmenu", (ev) => {
  const row = ev.target.closest(".row");
  if (!row) return;
  ev.preventDefault();
  selectRow(row);
  const dir = row.dataset.dir !== undefined;
  const path = dir ? row.dataset.dir : row.dataset.path;
  showMenu(ev.clientX, ev.clientY, [
    dir ? { label: row.getAttribute("aria-expanded") === "true" ? "Collapse" : "Expand", run: () => row.setOpen(row.getAttribute("aria-expanded") !== "true") }
      : { label: "Open", run: () => guarded(() => openFile(path)) },
    "-",
    { label: "Copy Relative Path", run: () => copyText(path, "the path") },
  ]);
});

// ------------------------------------------------------------------ keyboard shortcuts

// Inside the terminal, on Windows and Linux, Ctrl+B/J/P/E are the shell's own (back, newline, history, end of line): only these are taken.
const TAKEN_IN_THE_TERMINAL = new Set(["palette", "shell", "closeTab"]);

const bindingsOf = (command) => [command.keys, ...(command.also || [])].filter(Boolean);

document.addEventListener("keydown", (ev) => {
  if (ev.isComposing) return;
  if (paletteOpen()) {                      // over the palette only the keys that open it are ours: the browser would print the page (Cmd+P)
    const again = COMMANDS.find((c) => (c.id === "quickOpen" || c.id === "palette") && bindingsOf(c).some((b) => matchesKey(ev, b, IS_MAC)));
    if (again) { ev.preventDefault(); ev.stopPropagation(); again.run(); }
    return;
  }
  if (modalOpen()) return;
  const target = ev.target;
  const inTerminal = !!target.closest?.(".term-holder");
  if (!inTerminal && target.matches?.("input, textarea, select, [contenteditable='true']")) return;      // typing in a field: leave the keys alone
  for (const command of COMMANDS) {
    if (!bindingsOf(command).some((b) => matchesKey(ev, b, IS_MAC))) continue;
    if (!IS_MAC && inTerminal && !TAKEN_IN_THE_TERMINAL.has(command.id)) return;
    ev.preventDefault();
    ev.stopPropagation();
    command.run();
    return;
  }
}, true);

// ------------------------------------------------------------------ your tabs come back after a reload

let tabsReady = false;       // saving starts once the saved tabs were read: the first render shows only the Verdict and would overwrite them
const tabsKey = () => `verdict.tabs:${sid}`;

function saveTabs() {                                      // (renderTabs calls this each time the tabs change)
  if (!tabsReady || !sid) return;
  const open = [...tabs].filter(([key, t]) => t.closable && !isSession(key)).map(([key]) => key);
  try { localStorage.setItem(tabsKey(), JSON.stringify({ open, active: activeTab })); } catch { /* storage unavailable */ }
}

async function restoreTabs() {
  try {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(tabsKey()) || "null"); } catch { /* unreadable: start clean */ }
    if (!saved || !Array.isArray(saved.open)) return;
    for (const key of saved.open) {
      if (typeof key !== "string") continue;
      if (key.startsWith("pdf:")) { if (session.subjects.some((s) => s.name === key.slice(4))) await openSubject(key.slice(4)); }
      else if (session.repo) await openFile(key).catch(() => {});             // a file that is gone is simply not reopened
    }
    if (tabs.has(saved.active)) showTab(saved.active);
    else if (!saved.open.includes(saved.active)) showTab("overview");     // it was claude, the shell or verdict.md: those are not brought back
  } finally {
    tabsReady = true;
    saveTabs();
  }
}

appReady.then(restoreTabs);
