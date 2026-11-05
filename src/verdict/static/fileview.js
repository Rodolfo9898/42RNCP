"use strict";

// Files and subject PDFs in the editor area: the code view (line numbers, current line, Ln/Col, find, minimap, breadcrumbs, go to line).
// Everything shown comes from untrusted input: DOM is built with textContent only.

const editorLineHeight = () => Math.round(settings.get("editor.fontSize") * 1.55 * zoomFactor());

function applyEditorSettings() {
  const root = document.documentElement.style;
  root.setProperty("--editor-font-size", `${Math.round(settings.get("editor.fontSize") * zoomFactor() * 100) / 100}px`);
  root.setProperty("--editor-line-height", `${editorLineHeight()}px`);
  root.setProperty("--editor-tab-size", String(settings.get("editor.tabSize")));
  root.setProperty("--zoom", String(zoomFactor()));
  document.body.classList.toggle("no-line-numbers", settings.get("editor.lineNumbers") === "off");
}

// Highlighted files arrive as [class, text] pairs per line; build spans with textContent only.
function sourceNodes(file, lines) {
  if (!file.tokens || file.tokens.length !== lines.length) return [file.content];
  const colored = settings.get("editor.bracketPairColorization.enabled") && rainbowEnabled(file.language);
  const tokens = colored ? rainbow(file.tokens) : file.tokens;      // brackets coloured by nesting depth
  const nodes = [];
  tokens.forEach((line, i) => {
    for (const [cls, text, level] of line) {
      const classes = [cls && `t-${cls}`, level !== undefined && `rb rb-${level < 0 ? "x" : level}`].filter(Boolean).join(" ");
      nodes.push(classes ? h("span", { class: classes }, text) : text);
    }
    if (i < tokens.length - 1) nodes.push("\n");
  });
  return nodes;
}

function buildFileView(path, file) {
  const view = h("div", { class: "view code-view", tabindex: "-1" });
  const built = { view, setMode: null, text: "", srcEl: null, codeEl: null };
  if (file.binary) { view.append(h("div", { class: "notice" }, `${path} is a binary file (${file.size} bytes).`)); return built; }
  const lines = file.content.split("\n");
  built.text = file.content;
  const notice = file.truncated ? h("div", { class: "notice" }, "File truncated to 1 MB.") : null;
  const gutter = h("div", { class: "gutter" }, lines.map((_, i) => i + 1).join("\n"));
  const src = h("pre", { class: "src" }, ...sourceNodes(file, lines));
  const code = h("div", { class: "code" }, gutter, src);
  built.srcEl = src;
  built.codeEl = code;
  gutter.addEventListener("mousedown", (ev) => {
    const lh = editorLineHeight();
    const line = Math.floor((ev.clientY - gutter.getBoundingClientRect().top - 4) / lh) + 1;
    if (line >= 1 && line <= lines.length) { ev.preventDefault(); selectLineOf(path, line); }
  });
  if (isMarkdownPath(path)) {
    const rendered = h("div", { class: "md-preview" }, renderMarkdown(file.content));
    const buttons = {
      preview: h("button", { onclick: () => built.setMode("preview") }, "Preview"),
      code: h("button", { onclick: () => built.setMode("code") }, "Code"),
    };
    built.setMode = (mode) => {
      rendered.hidden = mode !== "preview";
      code.hidden = mode !== "code";
      for (const [name, button] of Object.entries(buttons)) button.classList.toggle("active", name === mode);
      bus.emit("fileview:mode", path, mode);
    };
    appendNodes(view, h("div", { class: "md-bar" }, buttons.preview, buttons.code, h("span", {}, "Markdown")), notice, rendered, code);
  } else appendNodes(view, notice, code);
  view.addEventListener("scroll", () => bus.emit("fileview:scroll", path), { passive: true });
  return built;
}

async function openFile(path, line, { preview = false, group = null, column = null } = {}) {
  let tab = tabs.get(path);
  let file = null;
  if (!tab) {
    file = await api(`sessions/${sid}/file?path=${encodeURIComponent(path)}`);
    tab = tabs.get(path);                                   // (a double click starts this twice: the second to arrive finds the tab the first made)
  }
  if (tab && !preview) pinTab(path);                       // opened on purpose (a reference, quick open, a double click): it stays
  if (!tab) {
    const built = buildFileView(path, file);
    const target = group && editors.groups[group] ? group : editors.active;
    if (preview) closePreviews(target);
    const name = path.split("/").pop();
    addTab(path, name, built.view, true, { group: target });
    tab = tabs.get(path);
    Object.assign(tab, {
      preview, tooltip: path, path, kind: "file", repoFile: true, setMode: built.setMode, text: built.text, srcEl: built.srcEl, codeEl: built.codeEl,
      language: file.language || (file.binary ? "binary" : "plain text"), binary: !!file.binary, tokens: file.tokens ?? null,
      iconEl: () => fileIcon(iconFor(name)),
    });
    if (built.setMode) built.setMode(defaultViewMode(path, line));       // README.md opens rendered; a file:line reference opens the source
    trackSelection(tab);
  }
  showTab(path);
  if (line) revealLine(path, line, column);
  return tab;
}

// The setting that colours the brackets changed: the files on show are built again from the same tokens.
function rebuildSources() {
  for (const tab of tabs.values()) {
    if (!tab.srcEl || !tab.tokens) continue;
    const lines = tab.text.split("\n");
    tab.srcEl.replaceChildren(...sourceNodes({ tokens: tab.tokens, content: tab.text, language: tab.language }, lines));
  }
}

// ------------------------------------------------------------------ the line you are on

function trackSelection(tab) {
  tab.view.addEventListener("mouseup", () => queueMicrotask(() => reportCursor(tab)));
  tab.view.addEventListener("keyup", () => reportCursor(tab));
}

// Offset in the text of a file of a point of the selection.
function textOffset(root, node, offset) {
  const range = document.createRange();
  range.setStart(root, 0);
  range.setEnd(node, offset);
  return range.toString().length;
}

function reportCursor(tab) {
  if (!tab.srcEl || !tab.text) return;
  const sel = document.getSelection();
  if (!sel || !sel.anchorNode || !tab.srcEl.contains(sel.anchorNode)) return;
  const at = textOffset(tab.srcEl, sel.anchorNode, sel.anchorOffset);
  const { line, col } = lineColumn(tab.text, at);
  tab.cursor = { line, col, selected: sel.isCollapsed ? 0 : sel.toString().length };
  showCurrentLine(tab, line, sel.isCollapsed);
  bus.emit("cursor", tab.key, tab.cursor);
}

function showCurrentLine(tab, line, collapsed) {
  for (const old of $$(".current-line", tab.srcEl)) old.remove();
  if (!collapsed) return;
  tab.srcEl.append(h("div", { class: "current-line", style: `top:calc(4px + ${(line - 1) * editorLineHeight()}px)` }));
}

function selectLineOf(path, line) {
  const tab = tabs.get(path);
  if (!tab || !tab.srcEl) return;
  const lines = tab.text.split("\n");
  let start = 0;
  for (let i = 0; i < line - 1; i++) start += lines[i].length + 1;
  selectOffsets(tab.srcEl, start, start + lines[line - 1].length);
  reportCursor(tab);
}

// Select characters [from, to) of the text in `root`.
function selectOffsets(root, from, to) {
  const walker = document.createTreeWalker(root, 4 /* SHOW_TEXT */);
  let seen = 0, startNode = null, startOffset = 0, endNode = null, endOffset = 0;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const len = node.nodeValue.length;
    if (!startNode && from <= seen + len) { startNode = node; startOffset = from - seen; }
    if (!endNode && to <= seen + len) { endNode = node; endOffset = to - seen; break; }
    seen += len;
  }
  if (!startNode || !endNode) return;
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  const sel = document.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
}

// Scroll to a line (and a column) of a file and mark it, as Go to Line and a click on a problem do.
function revealLine(path, line, column = null, length = 0) {
  const tab = tabs.get(path);
  if (!tab || !tab.codeEl) return;
  if (tab.setMode) tab.setMode("code");
  const lh = editorLineHeight();
  for (const old of $$(".hl", tab.codeEl)) old.remove();
  tab.codeEl.append(h("div", { class: "hl at", style: `top:${4 + (line - 1) * lh}px` }));
  const view = tab.view;
  view.scrollTop = Math.max(0, (line - 1) * lh - (view.clientHeight || 400) / 2);
  if (column !== null && length) {
    const lines = tab.text.split("\n");
    let start = 0;
    for (let i = 0; i < line - 1; i++) start += lines[i].length + 1;
    selectOffsets(tab.srcEl, start + column, start + column + length);
  }
  rememberLocation(path, line);
  tab.cursor = { line, col: (column ?? 0) + 1, selected: length };
  bus.emit("cursor", path, tab.cursor);
}

// ------------------------------------------------------------------ subject PDFs

// Subject PDFs open in a tab like a file: one image per page, rendered by the server.
async function openSubject(name, page = 1, group = null) {
  const key = `pdf:${name}`;
  let tab = tabs.get(key);
  if (!tab) {
    const subject = session.subjects.find((s) => s.name === name);
    if (!subject) return notify(`${name} is not loaded in this review.`, { level: "warning" });
    const base = `/api/sessions/${sid}/subjects/${encodeURIComponent(name)}/pages`;
    const view = h("div", { class: "view pdf" }, Array.from({ length: subject.pages }, (_, i) => h("figure", { "data-page": i + 1 },
      h("img", { src: `${base}/${i + 1}.png`, alt: `${name}, page ${i + 1}`, loading: "lazy" }),
      h("figcaption", {}, `page ${i + 1} of ${subject.pages}`))));
    addTab(key, name, view, true, { group: group && editors.groups[group] ? group : editors.active });
    tab = tabs.get(key);
    Object.assign(tab, { language: "PDF", kind: "pdf", iconEl: () => fileIcon(iconFor(name)), subject: name });
  }
  showTab(key);
  $(`figure[data-page="${page}"]`, tab.view)?.scrollIntoView?.({ block: "start" });
}

const pageLink = (pdf, page) => h("a", { href: "#", class: "page-link", onclick: (ev) => { ev.preventDefault(); ev.stopPropagation(); guarded(() => openSubject(pdf, page)); } },
  `${pdf} p.${page}`);

// ------------------------------------------------------------------ breadcrumbs

function renderBreadcrumbs(groupId) {
  const parts = groupEls.get(groupId);
  const key = editors.groups[groupId].active;
  const tab = key ? tabs.get(key) : null;
  const show = settings.get("breadcrumbs.enabled") && tab && (tab.path || tab.kind === "pdf");
  parts.crumbs.hidden = !show;
  if (!show) { parts.crumbs.replaceChildren(); return; }
  const trail = tab.kind === "pdf" ? [{ name: "Subjects", path: "", last: false }, { name: tab.subject, path: tab.subject, last: true }] : breadcrumbParts(tab.path);
  const symbol = tab.path && tab.text ? symbolAt(tab) : null;
  parts.crumbs.replaceChildren(...trail.flatMap((part, i) => [
    i ? icon("chevron-right", 12) : null,
    h("button", {
      class: `crumb ${part.last && !symbol ? "last" : ""}`, title: part.path || part.name,
      onclick: (ev) => { if (tab.kind === "file") showMenuAt(ev.currentTarget, siblingItems(part)); },
    }, part.last && tab.kind === "file" ? [h("span", { class: "crumb-icon" }, fileIcon(iconFor(part.name))), part.name] : part.name),
  ]), symbol ? icon("chevron-right", 12) : null, symbol ? h("button", { class: "crumb last", title: `${symbol.kind} ${symbol.name}`, onclick: () => runCommand("workbench.action.gotoSymbol") }, symbol.name) : null);
}

// What the folder of a crumb holds: the entries to choose from, as in VS Code.
function siblingItems(part) {
  const folder = part.last ? part.path.split("/").slice(0, -1).join("/") : part.path;
  const entries = (typeof treeEntries !== "undefined" ? treeEntries : []).filter((e) => {
    const parent = e.path.includes("/") ? e.path.slice(0, e.path.lastIndexOf("/")) : "";
    return parent === (part.last ? folder : part.path);
  });
  const name = (e) => e.path.split("/").pop();
  entries.sort((a, b) => (a.type === b.type ? name(a).localeCompare(name(b)) : a.type === "dir" ? -1 : 1));
  if (!entries.length) return [{ label: "No siblings", disabled: true }];
  return entries.slice(0, 40).map((e) => e.type === "dir"
    ? { label: `${name(e)}/`, run: () => runCommand("workbench.files.revealInExplorer", e.path) }
    : { label: name(e), checked: e.path === part.path, run: () => guarded(() => openFile(e.path)) });
}

// The function (or heading) the top of the view is in.
function symbolAt(tab) {
  const symbols = outlineOfTab(tab);
  if (!symbols.length) return null;
  const top = Math.floor((tab.view.scrollTop || 0) / editorLineHeight()) + 1;
  const line = tab.cursor?.line ?? top;
  let found = null;
  for (const s of symbols) { if (s.line <= line) found = s; else break; }
  return found;
}

const outlineOfTab = (tab) => {
  if (!tab || !tab.text) return [];
  tab.outline ??= outlineOf(tab.text, tab.language);
  return tab.outline;
};

// ------------------------------------------------------------------ find in the file in front (Cmd+F)

const find = { widget: null, group: null, query: "", caseSensitive: false, word: false, regex: false, matches: [], index: -1, error: "", timer: null };

function buildFindWidget() {
  if (find.widget) return find.widget;
  const input = h("input", { type: "text", placeholder: "Find", spellcheck: "false", autocomplete: "off", "aria-label": "Find" });
  const toggle = (label, title, key) => h("button", { class: "find-toggle", title, "aria-label": title, "aria-pressed": "false", onclick: () => { find[key] = !find[key]; syncFind(); runFind(); input.focus(); } }, label);
  const count = h("span", { class: "find-count" });
  const widget = h("div", { class: "find-widget", role: "dialog", "aria-label": "Find" },
    input, toggle("Aa", "Match Case (Alt+C)", "caseSensitive"), toggle("ab", "Match Whole Word (Alt+W)", "word"), toggle(".*", "Use Regular Expression (Alt+R)", "regex"),
    count,
    iconButton("arrow-up", "Previous Match (Shift+Enter)", () => stepFind(-1)),
    iconButton("arrow-down", "Next Match (Enter)", () => stepFind(1)),
    iconButton("x", "Close (Escape)", closeFind));
  input.addEventListener("input", () => { find.query = input.value; clearTimeout(find.timer); find.timer = setTimeout(runFind, 40); });
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); stepFind(ev.shiftKey ? -1 : 1); }
    else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeFind(); }
    else if (ev.altKey && ev.code === "KeyC") { ev.preventDefault(); find.caseSensitive = !find.caseSensitive; syncFind(); runFind(); }
    else if (ev.altKey && ev.code === "KeyW") { ev.preventDefault(); find.word = !find.word; syncFind(); runFind(); }
    else if (ev.altKey && ev.code === "KeyR") { ev.preventDefault(); find.regex = !find.regex; syncFind(); runFind(); }
  });
  find.widget = widget;
  find.input = input;
  find.count = count;
  return widget;
}

function syncFind() {
  const buttons = $$(".find-toggle", find.widget);
  [find.caseSensitive, find.word, find.regex].forEach((on, i) => { buttons[i].classList.toggle("on", on); buttons[i].setAttribute("aria-pressed", String(on)); });
}

function openFind(seed = null) {
  const tab = tabs.get(activeTab);
  if (!tab || !tab.text) { notify("Open a text file first to find in it.", { level: "info" }); return; }
  const widget = buildFindWidget();
  const parts = groupEls.get(groupOf(activeTab));
  parts.body.append(widget);
  find.group = groupOf(activeTab);
  widget.hidden = false;
  setContext("findWidgetVisible", true);
  const selected = seed ?? (document.getSelection()?.toString() || "");
  if (selected && !selected.includes("\n") && selected.length < 200) { find.query = selected; find.input.value = selected; }
  else find.input.value = find.query;
  syncFind();
  find.input.focus();
  find.input.select();
  runFind(false);
}

function closeFind() {
  if (!find.widget || find.widget.hidden) return;
  find.widget.hidden = true;
  paintFind(null);
  setContext("findWidgetVisible", false);
  const tab = tabs.get(activeTab);
  tab?.view.focus({ preventScroll: true });
}

function runFind(reveal = true) {
  const tab = tabs.get(activeTab);
  if (!find.widget || find.widget.hidden || !tab || !tab.text) { paintFind(null); return; }
  const { matches, error } = findMatches(tab.text, find.query, { caseSensitive: find.caseSensitive, word: find.word, regex: find.regex });
  find.matches = matches;
  find.error = error;
  const from = tab.cursor ?? { line: 1, col: 1 };
  find.index = matches.length ? nextMatch(matches, from.line, from.col - 1) : -1;
  paintFind(tab);
  if (reveal && find.index >= 0) scrollToMatch(tab);
}

function stepFind(step) {
  const tab = tabs.get(activeTab);
  if (!find.matches.length || !tab) return;
  find.index = (find.index + step + find.matches.length) % find.matches.length;
  paintFind(tab);
  scrollToMatch(tab);
}

function scrollToMatch(tab) {
  const m = find.matches[find.index];
  if (!m) return;
  const lh = editorLineHeight();
  const top = (m.line - 1) * lh, view = tab.view, h2 = view.clientHeight || 400;
  if (top < view.scrollTop || top + lh > view.scrollTop + h2) view.scrollTop = Math.max(0, top - h2 / 2);
  tab.cursor = { line: m.line, col: m.col + 1, selected: m.length };
  bus.emit("cursor", tab.key, tab.cursor);
}

// The matches drawn behind the text: a box for each, the current one in another colour.
function paintFind(tab) {
  for (const t of tabs.values()) if (t.srcEl) for (const old of $$(".find-hl", t.srcEl)) old.remove();
  if (find.count) {
    find.count.textContent = !find.query ? "" : find.error ? "Invalid" : find.matches.length ? `${find.index + 1} of ${find.matches.length}` : "No results";
    find.count.classList.toggle("none", !!find.query && !find.matches.length);
  }
  if (!tab || !tab.srcEl || !find.matches.length) return;
  const lh = editorLineHeight(), tabSize = settings.get("editor.tabSize");
  const lines = tab.text.split("\n");
  const frag = document.createDocumentFragment();
  find.matches.slice(0, 3000).forEach((m, i) => {
    const text = lines[m.line - 1] ?? "";
    const left = visualColumn(text, m.col, tabSize), width = visualColumn(text, m.col + m.length, tabSize) - left;
    frag.append(h("div", { class: `find-hl ${i === find.index ? "current" : ""}`, style: `top:calc(4px + ${(m.line - 1) * lh}px);left:calc(4px + ${left}ch);width:${width}ch;height:${lh}px` }));
  });
  tab.srcEl.append(frag);
}

bus.on("tab:active", () => { if (find.widget && !find.widget.hidden) { const g = groupOf(activeTab); if (g && g !== find.group) { groupEls.get(g).body.append(find.widget); find.group = g; } runFind(false); } });
