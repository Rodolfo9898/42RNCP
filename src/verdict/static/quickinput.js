"use strict";

// The quick input: Go to File (Cmd+P), the command palette (Cmd+Shift+P, or ">" in the box), Go to Symbol ("@"), Go to Line (":42"),
// and the lists the commands ask the user to pick from (the colour theme, a view to open).

const quick = { root: null, input: null, list: null, title: null, items: [], at: 0, mode: "files", picker: null, focusBack: null, resolve: null };
const RECENT_COMMANDS = "verdict.recentCommands";

function buildQuickInput() {
  if (quick.root) return;
  const input = h("input", { type: "text", spellcheck: "false", autocomplete: "off", "aria-label": "Quick input" });
  const list = h("div", { class: "palette-list", role: "listbox" });
  const title = h("div", { class: "palette-title" });
  const root = h("div", { id: "palette", hidden: true }, h("div", { class: "palette-box" }, title, input, list));
  root.addEventListener("mousedown", (ev) => { if (ev.target === root) closeQuickInput(); });
  input.addEventListener("input", refreshQuick);
  input.addEventListener("blur", () => setTimeout(() => { if (!root.contains(document.activeElement)) closeQuickInput(); }, 0));
  list.addEventListener("mousedown", (ev) => ev.preventDefault());                    // (a click on an item must not take the focus first)
  input.addEventListener("keydown", (ev) => {
    const last = quick.items.length - 1;
    const move = (to) => { ev.preventDefault(); quick.at = to; markQuick(); quick.picker?.onHighlight?.(quick.items[quick.at]); };
    if (ev.key === "ArrowDown") move(quick.at >= last ? 0 : quick.at + 1);
    else if (ev.key === "ArrowUp") move(quick.at <= 0 ? last : quick.at - 1);
    else if (ev.key === "PageDown") move(Math.min(last, quick.at + 8));
    else if (ev.key === "PageUp") move(Math.max(0, quick.at - 8));
    else if (ev.key === "Home" && ev.ctrlKey) move(0);
    else if (ev.key === "End" && ev.ctrlKey) move(last);
    else if (ev.key === "Enter") { ev.preventDefault(); acceptQuick(quick.at); }
    else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeQuickInput(); }
    else if (ev.key === "Tab") ev.preventDefault();                                   // (the focus stays in the box)
  });
  document.body.append(root);
  Object.assign(quick, { root, input, list, title });
}

const quickOpen = () => !!quick.root && !quick.root.hidden;

function closeQuickInput(value = null) {
  if (!quickOpen()) return;
  quick.root.hidden = true;
  const back = quick.focusBack, resolve = quick.resolve, picker = quick.picker;
  Object.assign(quick, { focusBack: null, resolve: null, picker: null });
  setContext("quickInputVisible", false);
  quick.input.blur();
  if (value === null) picker?.onCancel?.();
  if (back && document.contains(back)) back.focus();
  resolve?.(value);
}

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

function renderQuick() {
  if (!quick.items.length) { quick.list.replaceChildren(h("div", { class: "palette-empty" }, quick.picker?.empty ?? "No matching results")); return; }
  let separatorBefore = null;
  quick.list.replaceChildren(...quick.items.flatMap((item, i) => {
    const row = h("div", {
      class: `palette-item ${i === quick.at ? "selected" : ""}`, role: "option", "aria-selected": String(i === quick.at),
      onmousemove: () => { if (quick.at !== i) { quick.at = i; markQuick(); quick.picker?.onHighlight?.(item); } },
      onclick: () => acceptQuick(i),
    }, item.iconEl ?? (item.iconSrc !== undefined ? fileIcon(item.iconSrc) : null), h("span", { class: "pi-label" }, ...marked(item.label, item.positions ?? [], item.offset || 0)),
    item.detail ? h("span", { class: "pi-detail" }, ...(item.detailIsPath ? marked(item.detail, item.positions ?? [], 0) : [item.detail])) : null,
    item.key ? h("span", { class: "pi-key" }, item.key) : null);
    const head = item.section && item.section !== separatorBefore ? (separatorBefore = item.section, h("div", { class: "palette-section" }, item.section)) : null;
    return head ? [head, row] : [row];
  }));
}

function markQuick() {
  $$(".palette-item", quick.list).forEach((el, i) => { el.classList.toggle("selected", i === quick.at); el.setAttribute("aria-selected", String(i === quick.at)); });
  $$(".palette-item", quick.list)[quick.at]?.scrollIntoView?.({ block: "nearest" });
}

// ------------------------------------------------------------------ what the box lists, by what has been typed

function rankItems(items, query, limit = 60) {
  const out = [];
  for (const item of items) {
    const match = fuzzyMatch(query, item.search ?? item.label);
    if (!match) continue;
    out.push({ ...item, score: match.score + (item.boost || 0), positions: match.positions });
  }
  out.sort((a, b) => b.score - a.score || (a.order ?? 0) - (b.order ?? 0) || (a.search ?? a.label).length - (b.search ?? b.label).length);
  return out.slice(0, limit);
}

function fileItems() {
  const open = [...tabHistory].reverse().filter((k) => tabs.has(k) && tabs.get(k).path);
  const items = [];
  treeEntries.filter((e) => e.type === "file").sort((a, b) => a.path.localeCompare(b.path)).forEach((e, order) => {
    const name = e.path.slice(e.path.lastIndexOf("/") + 1), dir = e.path.slice(0, Math.max(0, e.path.length - name.length - 1));
    items.push({ search: e.path, label: name, detail: dir, detailIsPath: true, offset: e.path.length - name.length, order: 1000 + order, boost: open.includes(e.path) ? 40 - open.indexOf(e.path) : 0,
      iconSrc: iconFor(name), path: e.path });
  });
  for (const s of session?.subjects ?? []) items.push({ search: s.name, label: s.name, detail: "subject PDF", offset: 0, order: 500, boost: tabs.has(`pdf:${s.name}`) ? 40 : 0, iconSrc: iconFor(s.name), subject: s.name });
  return items;
}

function commandItems(query) {
  const recent = store.get(RECENT_COMMANDS, []);
  const items = [...commandRegistry.values()].filter((c) => !c.hidden && (!c.enabled || c.enabled())).map((c, order) => ({
    search: commandTitle(c), label: commandTitle(c), key: keyLabel(c.id), order, command: c.id,
    boost: query ? 0 : recent.includes(c.id) ? 100 - recent.indexOf(c.id) : 0, section: !query && recent.includes(c.id) ? "recently used" : (!query ? "other commands" : undefined),
  }));
  if (!query) items.sort((a, b) => (b.boost - a.boost) || a.search.localeCompare(b.search));
  return items;
}

function symbolItems() {
  const tab = tabs.get(activeTab);
  return outlineOfTab(tab).map((s, order) => ({ search: s.name, label: s.name, detail: `${s.kind}, line ${s.line}`, offset: 0, order, line: s.line, path: tab.path }));
}

// "src/main.c:42:7" is the file and where to go in it; "main" alone is just the file.
function splitPlace(text) {
  const m = /^(.*?)(?::(\d+))?(?::(\d+))?$/.exec(text);
  return m && m[2] ? { query: m[1], line: Number(m[2]), col: m[3] ? Number(m[3]) : null } : { query: text, line: null, col: null };
}

function refreshQuick() {
  if (quick.picker) {
    const query = quick.input.value;
    quick.items = query ? rankItems(quick.picker.items.map((i) => ({ search: i.label, ...i })), query, 200) : quick.picker.items.map((i) => ({ ...i, positions: [] }));
    quick.at = Math.max(0, quick.items.findIndex((i) => i.picked));
    renderQuick();
    quick.picker.onHighlight?.(quick.items[quick.at]);
    return;
  }
  const text = quick.input.value;
  const prefix = text[0];
  const placeholders = { ">": "Type the name of a command to run.", "@": "Go to a symbol in the editor", ":": "Type a line number to go to (and optionally a column: 42:7)", "%": "Search for text in the files of the project", "?": "Type '?' to get help on the actions you can take from here" };
  quick.input.placeholder = placeholders[prefix] ?? "Search files by name (append :line to go to a line, @ for symbols, > for commands)";
  if (prefix === ">") {
    quick.mode = "commands";
    quick.items = rankItems(commandItems(text.slice(1).trim()), text.slice(1), 80);
  } else if (prefix === "@") {
    quick.mode = "symbols";
    quick.items = rankItems(symbolItems(), text.slice(1), 200);
  } else if (prefix === ":") {
    quick.mode = "line";
    const [line, col] = text.slice(1).split(/[:,]/).map((x) => Number.parseInt(x, 10));
    const tab = tabs.get(activeTab);
    const total = tab?.text ? tab.text.split("\n").length : 0;
    quick.items = tab?.text ? [{ label: Number.isFinite(line) ? `Go to line ${Math.min(Math.max(line, 1), total)}${Number.isFinite(col) ? ` and column ${col}` : ""}.` : `Current line: ${tab.cursor?.line ?? 1}. Type a line number between 1 and ${total} to navigate to.`, goto: Number.isFinite(line) ? { line: Math.min(Math.max(line, 1), total), col: Number.isFinite(col) ? col : null } : null, positions: [] }] : [{ label: "Open a text file first to go to a line.", goto: null, positions: [] }];
  } else if (prefix === "%") {
    quick.mode = "text";
    quick.items = [{ label: text.length > 1 ? `Search for "${text.slice(1)}" in the files` : "Type the text to search for", text: text.slice(1), positions: [] }];
  } else if (prefix === "?") {
    quick.mode = "help";
    quick.items = [["", "Go to File"], [">", "Show and Run Commands"], ["@", "Go to Symbol in Editor"], [":", "Go to Line/Column"], ["%", "Find in Files"]].map(([p, label]) => ({ label: `${p || "(nothing)"}  ${label}`, prefixTo: p, positions: [] }));
  } else {
    quick.mode = "files";
    const { query } = splitPlace(text);
    quick.items = rankItems(fileItems(), query);
  }
  quick.at = 0;
  renderQuick();
}

function acceptQuick(index) {
  const item = quick.items[index];
  if (!item) return;
  if (quick.picker) { closeQuickInput(item); return; }
  if (item.prefixTo !== undefined) { quick.input.value = item.prefixTo; refreshQuick(); return; }
  const place = splitPlace(quick.input.value);
  const mode = quick.mode;
  closeQuickInput();
  guarded(async () => {
    if (mode === "commands") {
      store.set(RECENT_COMMANDS, [item.command, ...store.get(RECENT_COMMANDS, []).filter((c) => c !== item.command)].slice(0, 8));
      await runCommand(item.command);
    } else if (mode === "symbols") revealLine(item.path, item.line);
    else if (mode === "line") { if (item.goto) revealLine(activeTab, item.goto.line, item.goto.col ? item.goto.col - 1 : null); }
    else if (mode === "text") { if (item.text) findInFiles(item.text); }
    else if (item.subject) await openSubject(item.subject);
    else if (item.path) await openFile(item.path, place.line ?? undefined, { column: place.col ? place.col - 1 : null });
  });
}

// Show the box. `prefill`: what is typed in it already (">" for the command palette, ":" for Go to Line).
function openQuickInput(prefill = "") {
  buildQuickInput();
  closeMenus();
  if (!quickOpen()) quick.focusBack = document.activeElement;
  quick.picker = null;
  quick.title.hidden = true;
  quick.root.hidden = false;
  setContext("quickInputVisible", true);
  quick.input.value = prefill;
  quick.input.focus();
  refreshQuick();
}

// Ask the user to choose from a list. Resolves to the chosen item, or null. `onHighlight(item)` is called as the selection moves
// (the colour theme previews), `onCancel()` when the box is closed without a choice.
function quickPick({ items, placeholder = "", title = "", empty = "No matching results", onHighlight = null, onCancel = null }) {
  buildQuickInput();
  closeMenus();
  return new Promise((resolve) => {
    if (quickOpen()) { const earlier = quick.resolve; quick.resolve = null; earlier?.(null); }
    else quick.focusBack = document.activeElement;
    quick.picker = { items, empty, onHighlight, onCancel };
    quick.resolve = resolve;
    quick.title.textContent = title;
    quick.title.hidden = !title;
    quick.root.hidden = false;
    setContext("quickInputVisible", true);
    quick.input.value = "";
    quick.input.placeholder = placeholder;
    quick.input.focus();
    refreshQuick();
  });
}
