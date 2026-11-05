"use strict";

// The editor area: editor groups side by side or one above the other, each with its tab strip, breadcrumbs and views. Which tab is in which
// group, and how the groups are split, is kept by the pure model in model.js (groups*); this file draws it and handles the mouse.
// A "tab" is anything shown there: a file, a subject PDF, the verdict, claude's terminal, the settings.

const tabs = new Map();          // key -> { key, title, view, closable, preview, tooltip, language, kind, path, ... }
let editors = groupsNew();
let activeTab = "overview";
const tabHistory = [];           // keys, the latest shown last, across all groups
const groupEls = new Map();      // group id -> { el, tabsEl, list, actions, crumbs, body, watermark }
let gridSignature = "";
let draggedTab = null;           // { key } while a tab is being dragged

const activeGroupId = () => editors.active;
const groupOf = (key) => groupsGroupOf(editors, key);
const tabOf = (key) => tabs.get(key);

function setEditors(next) {
  editors = next;
  renderEditors();
  saveTabs();
}

// ------------------------------------------------------------------ tabs

// `view` goes into the group asked for (the active one by default). The tab is put in front.
function addTab(key, title, view, closable = true, { group = null, index = null } = {}) {
  tabs.set(key, { key, title, view, closable });
  view.dataset.key = key;
  editors = groupsOpen(editors, key, group, index);
  activeTab = key;
  renderEditors();
}

function showTab(key) {
  const tab = tabs.get(key);
  if (!tab) return;
  editors = groupsOpen(editors, key, groupOf(key));
  activeTab = key;
  const at = tabHistory.indexOf(key);
  if (at >= 0) tabHistory.splice(at, 1);
  tabHistory.push(key);
  renderEditors();
  rememberLocation(key);
  bus.emit("tab:active", key);
  saveTabs();
}

function closeTab(key) {
  const tab = tabs.get(key);
  if (!tab) return;
  if (tab.onClose) tab.onClose();
  tab.view.remove();
  tabs.delete(key);
  const at = tabHistory.indexOf(key);
  if (at >= 0) tabHistory.splice(at, 1);
  editors = groupsCloseTab(editors, key);
  activeTab = editors.groups[editors.active]?.active ?? tabHistory.filter((k) => tabs.has(k)).pop() ?? "";
  renderEditors();
  bus.emit("tab:active", activeTab);
  bus.emit("tab:closed", key);
  saveTabs();
}

function pinTab(key) {                       // double click (on the tab or in the explorer): keep it open
  const tab = tabs.get(key);
  if (tab && tab.preview) { tab.preview = false; renderEditors(); }
}

// A preview tab (shown in italics) is replaced by the next one opened in its group, until it is kept open.
function closePreviews(groupId) {
  for (const key of [...(editors.groups[groupId]?.tabs ?? [])]) if (tabs.get(key)?.preview) closeTab(key);
}

function moveTabToGroup(key, groupId, index = null) {
  if (!tabs.has(key) || !editors.groups[groupId]) return;
  setEditors(groupsOpen(editors, key, groupId, index));
  activeTab = key;
  bus.emit("tab:active", key);
}

// Beside a group, on the side asked ("left" | "right" | "up" | "down"), with the tab if one is named.
function splitGroup(groupId, side, key = null) {
  const { state, group } = groupsSplit(editors, groupId, side, key);
  setEditors(state);
  activeTab = editors.groups[group]?.active ?? activeTab;
  return group;
}

// Split Editor: an empty group beside this one. When the group has other tabs the one in front goes along (so that both sides show
// something); a group with a single tab keeps it, and the new group is where the next file opens.
function splitEditor(groupId, side, key = null) {
  const group = editors.groups[groupId];
  if (!group) return null;
  const moving = key ?? group.active;
  return splitGroup(groupId, side, group.tabs.length > 1 && moving ? moving : null);
}

function activateGroup(id) {
  if (editors.active === id || !editors.groups[id]) return;
  editors = groupsActivateGroup(editors, id);
  activeTab = editors.groups[id].active ?? "";
  renderEditors();
  bus.emit("tab:active", activeTab);
}

function closeGroup(id) {
  const { state, closed } = groupsCloseGroup(editors, id);
  for (const key of closed) {
    const tab = tabs.get(key);
    if (!tab || !tab.closable) continue;
    tab.onClose?.();
    tab.view.remove();
    tabs.delete(key);
  }
  const keep = closed.filter((k) => tabs.has(k));
  editors = state;
  for (const key of keep) editors = groupsOpen(editors, key, editors.active);                  // what cannot be closed goes to the group that is left
  renderEditors();
  activeTab = editors.groups[editors.active]?.active ?? "";
  bus.emit("tab:active", activeTab);
  saveTabs();
}

function closeTabs(mode, key) {
  const group = editors.groups[groupOf(key)];
  const entries = group.tabs.map((k) => ({ key: k, closable: tabs.get(k)?.closable !== false, session: isSession(k) }));
  for (const k of tabsToClose(entries, mode, key)) closeTab(k);
}

const isSession = (key) => key === "terminal" || key.startsWith("shell:");       // claude and the shells are conversations, not documents

function cycleTab(step) {
  const group = editors.groups[editors.active];
  if (!group || group.tabs.length < 2) return;
  const at = group.tabs.indexOf(group.active);
  showTab(group.tabs[(at + step + group.tabs.length) % group.tabs.length]);
}

function focusGroup(direction) {
  const target = groupsFocusDirection(editors, direction);
  if (target) { activateGroup(target); const key = editors.groups[target].active; if (key) showTab(key); }
}

function cycleGroup(step) {
  const ids = gridLeaves(editors.grid);
  const at = ids.indexOf(editors.active);
  activateGroup(ids[(at + step + ids.length) % ids.length]);
}

// ------------------------------------------------------------------ drawing the groups

function makeGroupElements(id) {
  const list = h("div", { class: "tab-list", role: "tablist", onwheel: (ev) => { if (ev.deltaY && !ev.deltaX) { list.scrollLeft += ev.deltaY; ev.preventDefault(); } } });
  const actions = h("div", { class: "group-actions" });
  const tabsEl = h("div", { class: "group-tabs" }, list, actions);
  const crumbs = h("div", { class: "group-breadcrumbs" });
  const watermark = h("div", { class: "group-watermark" });
  const body = h("div", { class: "group-body" }, watermark);
  const el = h("div", { class: "editor-group", "data-group": id, onmousedown: () => activateGroup(id) }, tabsEl, crumbs, body);
  wireGroupDrop(el, body, id);
  const parts = { el, tabsEl, list, actions, crumbs, body, watermark };
  groupEls.set(id, parts);
  return parts;
}

function buildGrid(node, path) {
  if (gridIsLeaf(node)) return groupEls.get(node.leaf).el;
  const el = h("div", { class: `grid-split grid-${node.dir}` });
  node.children.forEach((child, i) => {
    if (i) el.append(makeGridSash(el, node.dir, path, i));
    const built = buildGrid(child, [...path, i]);
    built.style.flex = `${node.sizes[i]} 1 0`;
    el.append(built);
  });
  return el;
}

// A divider between two groups (or two rows of groups): drag it to give one more room and the other less.
function makeGridSash(split, dir, path, index) {
  const sash = h("div", { class: `grid-sash grid-sash-${dir}`, role: "separator", tabindex: "0", "aria-orientation": dir === "row" ? "vertical" : "horizontal" });
  sash.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    sash.setPointerCapture?.(ev.pointerId);
    sash.classList.add("active");
    document.body.classList.add("resizing");
    const kids = [...split.children].filter((c) => !c.classList.contains("grid-sash"));
    const a = kids[index - 1], b = kids[index];
    const boxA = a.getBoundingClientRect(), boxB = b.getBoundingClientRect();
    const horizontal = dir === "row";
    const start = horizontal ? boxA.left : boxA.top;
    const total = (horizontal ? boxA.width + boxB.width : boxA.height + boxB.height) || 1;
    const node = nodeAt(editors.grid, path);
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
      sash.classList.remove("active");
      document.body.classList.remove("resizing");
      editors = { ...editors, grid: gridSetSizes(editors.grid, path, weights) };
      gridSignature = JSON.stringify(editors.grid);
      saveTabs();
      bus.emit("fit");
    }, { once: true });
  });
  sash.addEventListener("dblclick", () => {
    editors = { ...editors, grid: gridEqualize(editors.grid) };
    gridSignature = "";
    renderEditors();
  });
  return sash;
}

const nodeAt = (grid, path) => path.reduce((n, i) => n.children[i], grid);

function renderEditors() {
  const root = $("#editor-area");
  if (!root) return;
  const ids = gridLeaves(editors.grid);
  for (const id of ids) if (!groupEls.has(id)) makeGroupElements(id);
  for (const id of [...groupEls.keys()]) if (!ids.includes(id)) { groupEls.get(id).el.remove(); groupEls.delete(id); }
  const signature = JSON.stringify(editors.grid);
  if (signature !== gridSignature || !root.firstChild) {
    gridSignature = signature;
    const saved = new Map();
    for (const el of $$(".view, .tab-list", root)) if (el.scrollTop || el.scrollLeft) saved.set(el, [el.scrollTop, el.scrollLeft]);
    root.replaceChildren(buildGrid(editors.grid, []));
    for (const [el, [top, left]] of saved) { el.scrollTop = top; el.scrollLeft = left; }
  }
  for (const id of ids) renderGroup(id);
  setContext("multipleEditorGroups", ids.length > 1);
  setContext("fileEditor", !!tabs.get(activeTab)?.path);
  setContext("diffEditor", tabs.get(activeTab)?.kind === "diff");
  bus.emit("editors");
  bus.emit("fit");
}

function renderGroup(id) {
  const g = editors.groups[id];
  const parts = groupEls.get(id);
  parts.el.classList.toggle("active-group", id === editors.active);
  parts.tabsEl.hidden = !settings.get("workbench.editor.showTabs");
  parts.list.replaceChildren(...g.tabs.map((key) => tabElement(key, id, g)));
  parts.list.querySelector(".tab.active")?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  for (const key of g.tabs) {
    const tab = tabs.get(key);
    if (!tab) continue;
    if (tab.view.parentNode !== parts.body) parts.body.append(tab.view);
    tab.view.hidden = key !== g.active;
  }
  parts.watermark.hidden = g.tabs.length > 0;
  if (!g.tabs.length) renderWatermark(parts.watermark);
  const own = (g.active && tabs.get(g.active)?.actions ? tabs.get(g.active).actions() : []).map((a) => iconButton(a.icon, a.title, () => a.run(), { disabled: a.disabled }));
  parts.actions.replaceChildren(
    ...own,
    iconButton("split-right", `Split Editor Right (${keyLabel("workbench.action.splitEditor")})`, (ev) => splitEditor(id, ev.altKey ? "down" : "right")),
    iconButton("more", "More Actions...", (ev) => showMenuAt(ev.currentTarget, groupMenu(id))));
  renderBreadcrumbs(id);
  bus.emit("group:rendered", id);
}

function renderWatermark(el) {
  const row = (command, label) => h("tr", {}, h("td", {}, label), h("td", { class: "key" }, keyLabel(command)));
  el.replaceChildren(
    icon("verdict", 120),
    h("table", {}, h("tbody", {}, [
      row("workbench.action.showCommands", "Show All Commands"), row("workbench.action.quickOpen", "Go to File"),
      row("workbench.action.findInFiles", "Find in Files"), row("workbench.action.terminal.toggleTerminal", "Toggle Terminal"),
    ])));
}

function tabElement(key, groupId, group) {
  const tab = tabs.get(key);
  const active = group.active === key;
  const el = h("div", {
    class: `tab ${active ? "active" : ""} ${tab.preview ? "preview" : ""} ${groupId === editors.active ? "in-active-group" : ""}`, role: "tab", "aria-selected": String(active),
    "data-key": key, title: tab.tooltip || tab.title, draggable: "true",
    onclick: () => showTab(key),
    onmousedown: (ev) => { if (ev.button === 1) ev.preventDefault(); },                       // (no autoscroll cursor on a middle click)
    onauxclick: (ev) => { if (ev.button === 1 && tab.closable) { ev.preventDefault(); closeTab(key); } },
    oncontextmenu: (ev) => { ev.preventDefault(); showContextMenu(ev, tabMenu(key)); },
    ondblclick: () => pinTab(key),
    ondragstart: (ev) => { draggedTab = { key }; ev.dataTransfer.effectAllowed = "move"; ev.dataTransfer.setData("application/x-verdict-tab", key); document.body.classList.add("dragging-tab"); },
    ondragover: (ev) => {
      if (!draggedTab) return;
      ev.preventDefault();
      ev.stopPropagation();
      const box = el.getBoundingClientRect(), after = ev.clientX >= box.left + box.width / 2;
      el.classList.toggle("drop-before", !after);
      el.classList.toggle("drop-after", after);
    },
    ondragleave: () => el.classList.remove("drop-before", "drop-after"),
    ondrop: (ev) => {
      if (!draggedTab) return;
      ev.preventDefault();
      ev.stopPropagation();
      const box = el.getBoundingClientRect(), after = ev.clientX >= box.left + box.width / 2;
      const moving = draggedTab.key;
      endTabDrag();
      if (moving === key) return;
      const target = group.tabs.indexOf(key) + (after ? 1 : 0);
      const same = groupOf(moving) === groupId;
      if (same) setEditors(groupsMoveWithin(editors, moving, key, after));
      else moveTabToGroup(moving, groupId, target);
      showTab(moving);
    },
    ondragend: endTabDrag,
  }, tab.iconEl ? tab.iconEl() : null, h("span", { class: "tab-title" }, tab.title),
  tab.closable ? h("span", { class: "close", title: "Close", onclick: (ev) => { ev.stopPropagation(); closeTab(key); } }, icon("x", 14)) : null);
  return el;
}

function endTabDrag() {
  draggedTab = null;
  document.body.classList.remove("dragging-tab");
  if (typeof refreshPending !== "undefined" && refreshPending) queueMicrotask(refreshViews);
  for (const el of $$(".drop-before, .drop-after, .drop-zone-overlay")) { el.classList.remove("drop-before", "drop-after"); if (el.classList.contains("drop-zone-overlay")) el.remove(); }
}

// The body of a group takes a tab dropped on it (in the middle), or splits the group on the side nearest to where it was dropped.
function wireGroupDrop(groupEl, body, id) {
  let overlay = null;
  const clear = () => { overlay?.remove(); overlay = null; };
  body.addEventListener("dragover", (ev) => {
    const kind = draggedTab ? "tab" : (ev.dataTransfer?.types ?? []).includes("application/x-verdict-path") ? "file" : null;
    if (!kind) return;
    ev.preventDefault();
    const zone = dropZone(ev.clientX, ev.clientY, body.getBoundingClientRect());
    if (!overlay) { overlay = h("div", { class: "drop-zone-overlay" }); body.append(overlay); }
    overlay.dataset.zone = zone;
  });
  body.addEventListener("dragleave", (ev) => { if (!body.contains(ev.relatedTarget)) clear(); });
  body.addEventListener("drop", (ev) => {
    const zone = dropZone(ev.clientX, ev.clientY, body.getBoundingClientRect());
    const file = ev.dataTransfer?.getData?.("application/x-verdict-path");
    clear();
    if (draggedTab) {
      ev.preventDefault();
      const key = draggedTab.key;
      endTabDrag();
      if (zone === "center") { if (groupOf(key) !== id) moveTabToGroup(key, id); showTab(key); }
      else { splitGroup(id, zone, key); showTab(key); }
    } else if (file) {
      ev.preventDefault();
      activateGroup(id);
      if (zone !== "center") splitGroup(id, zone);
      guarded(() => openFile(file, undefined, {}));
    }
  });
}

// ------------------------------------------------------------------ menus on tabs and groups

function tabMenu(key) {
  const tab = tabs.get(key);
  const group = editors.groups[groupOf(key)];
  const at = group.tabs.indexOf(key);
  const others = group.tabs.filter((k) => k !== key && tabs.get(k)?.closable && !isSession(k)).length;
  const right = group.tabs.slice(at + 1).filter((k) => tabs.get(k)?.closable && !isSession(k)).length;
  return [
    { label: "Close", key: keyLabel("workbench.action.closeActiveEditor"), disabled: !tab.closable, run: () => closeTab(key) },
    { label: "Close Others", disabled: !others, run: () => closeTabs("others", key) },
    { label: "Close to the Right", disabled: !right, run: () => closeTabs("right", key) },
    { label: "Close All", disabled: !tabsToClose(group.tabs.map((k) => ({ key: k, closable: tabs.get(k)?.closable !== false, session: isSession(k) })), "all", key).length, run: () => closeTabs("all", key) },
    "-",
    ...(tab.preview ? [{ label: "Keep Open", run: () => pinTab(key) }] : []),
    { label: "Copy Path", disabled: !tab.path, run: () => copyText(tab.path, "the path") },
    { label: "Reveal in Explorer", disabled: !tab.path, run: () => runCommand("workbench.files.revealActiveFileInExplorer", key) },
    "-",
    { label: "Split Right", run: () => { splitEditor(groupOf(key), "right", key); } },
    { label: "Split Down", run: () => { splitEditor(groupOf(key), "down", key); } },
    ...(isSession(key) && tab.moveToPanel ? [{ label: "Move Terminal into Panel", run: () => tab.moveToPanel() }] : []),
  ];
}

function groupMenu(id) {
  const keys = editors.groups[id].tabs;
  const closable = keys.filter((k) => tabs.get(k)?.closable && !isSession(k));
  return [
    { label: "Show Opened Editors", disabled: !keys.length, run: () => runCommand("workbench.action.showEditorsInActiveGroup", id) },
    "-",
    { label: "Close All", disabled: !closable.length, run: () => closable.forEach(closeTab) },
    { label: "Close Editor Group", disabled: gridLeaves(editors.grid).length < 2 && !keys.length, run: () => closeGroup(id) },
    "-",
    { label: "Split Up", run: () => splitEditor(id, "up") }, { label: "Split Down", run: () => splitEditor(id, "down") },
    { label: "Split Left", run: () => splitEditor(id, "left") }, { label: "Split Right", run: () => splitEditor(id, "right") },
    "-",
    { label: "Show Tabs", checked: () => settings.get("workbench.editor.showTabs"), run: () => settings.set("workbench.editor.showTabs", !settings.get("workbench.editor.showTabs")) },
    { label: "Show Breadcrumbs", checked: () => settings.get("breadcrumbs.enabled"), run: () => settings.set("breadcrumbs.enabled", !settings.get("breadcrumbs.enabled")) },
    { label: "Show Minimap", checked: () => settings.get("editor.minimap.enabled"), run: () => settings.set("editor.minimap.enabled", !settings.get("editor.minimap.enabled")) },
  ];
}

// ------------------------------------------------------------------ going back and forward (Go > Back, Go > Forward)

const navigation = { places: [], at: -1, replaying: false };

function rememberLocation(key, line = null) {
  if (navigation.replaying || !key) return;
  const last = navigation.places[navigation.at];
  if (last && last.key === key && (line === null || last.line === line)) return;
  navigation.places.splice(navigation.at + 1);
  navigation.places.push({ key, line });
  if (navigation.places.length > 50) navigation.places.shift();
  navigation.at = navigation.places.length - 1;
}

function navigate(step) {
  let at = navigation.at + step;
  while (at >= 0 && at < navigation.places.length && !tabs.has(navigation.places[at].key)) at += step;       // (a tab that was closed is skipped)
  if (at < 0 || at >= navigation.places.length) return;
  navigation.at = at;
  navigation.replaying = true;
  try {
    const place = navigation.places[at];
    showTab(place.key);
    if (place.line) revealLine(place.key, place.line);
  } finally { navigation.replaying = false; }
}

// ------------------------------------------------------------------ the tabs come back after a reload

const tabsKey = () => `verdict.editors:${sid}`;
let tabsReady = false;        // saving starts once the saved tabs were read: the first render has only the Verdict and would overwrite them
let saveQueued = false;

function saveTabs() {
  if (!tabsReady || !sid || saveQueued) return;
  saveQueued = true;
  queueMicrotask(() => {
    saveQueued = false;
    const groups = {};
    for (const id of Object.keys(editors.groups)) {
      const g = editors.groups[id];
      groups[id] = { tabs: g.tabs.filter((k) => restorable(k)), active: g.active && restorable(g.active) ? g.active : null };
    }
    store.set(tabsKey(), { grid: editors.grid, groups, active: editors.active, next: editors.next });
  });
}

const restorable = (key) => key.startsWith("pdf:") || tabs.get(key)?.path === key || ["settings", "keybindings"].includes(key);

async function restoreTabs() {
  try {
    const saved = store.get(tabsKey(), null);
    if (!saved || !isRecord(saved.groups) || !saved.grid) return;
    const ids = gridLeaves(saved.grid);
    if (!ids.length || !ids.every((id) => isRecord(saved.groups[id]) && Array.isArray(saved.groups[id].tabs))) return;
    // the same groups as before, empty; what is open already (the Verdict) goes in the first
    const fresh = { grid: saved.grid, groups: {}, active: ids.includes(saved.active) ? saved.active : ids[0], next: Number.isFinite(saved.next) ? saved.next : ids.length + 1 };
    for (const id of ids) fresh.groups[id] = { tabs: [], active: null, history: [] };
    const first = fresh.groups[ids[0]];
    first.tabs.push(...tabs.keys());
    first.active = first.tabs.includes(editors.groups[editors.active]?.active) ? editors.groups[editors.active].active : first.tabs[0] ?? null;
    editors = fresh;
    gridSignature = "";
    renderEditors();
    for (const id of ids) {
      for (const key of saved.groups[id].tabs) {
        if (typeof key !== "string") continue;
        if (key === "settings") openSettings(id);
        else if (key === "keybindings") openKeybindings(id);
        else if (key.startsWith("pdf:")) { if (session.subjects.some((s) => s.name === key.slice(4))) await openSubject(key.slice(4), 1, id); }
        else if (session.repo) await openFile(key, undefined, { group: id }).catch(() => {});       // a file that is gone is simply not reopened
      }
      const wanted = saved.groups[id].active;
      if (typeof wanted === "string" && tabs.has(wanted) && groupOf(wanted) === id) editors = groupsOpen(editors, wanted, id);
    }
    const front = saved.groups[saved.active]?.active;
    editors = groupsActivateGroup(editors, ids.includes(saved.active) ? saved.active : ids[0]);
    if (typeof front === "string" && tabs.has(front)) showTab(front);
    else if (tabs.get(editors.groups[editors.active]?.active)) showTab(editors.groups[editors.active].active);
  } finally {
    tabsReady = true;
    renderEditors();
    saveTabs();
  }
}

function resetEditorLayout(preset) {
  setEditors(groupsPreset(editors, preset));
  activeTab = editors.groups[editors.active]?.active ?? activeTab;
}
