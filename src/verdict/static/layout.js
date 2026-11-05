"use strict";

// The workbench frame, as VS Code lays it out: an activity bar, a side bar, a secondary side bar and a panel around the editor area.
// What lives in the side bars and the panel are view containers (each holding views), and every container can be dragged from one of
// them to another. Where everything is is kept by the pure model in model.js (layout*); this file draws it and handles the mouse.

const LAYOUT_KEY = "verdict.workbench";
const containerSpecs = new Map();   // id -> { id, title, icon, location, order, badge?() }
const viewSpecs = new Map();        // id -> { id, container, title, order?, collapsed?, create(body, api), refresh?(), actions?() -> [{ icon, title, run, disabled? }] }
const panes = new Map();            // view id -> { el, header, body, actions, built }
let layout = null;

function registerContainer(spec) { containerSpecs.set(spec.id, spec); }
function registerView(spec) { viewSpecs.set(spec.id, spec); }

function modelRegistry() {
  const containers = [];
  for (const c of containerSpecs.values()) {
    const views = [...viewSpecs.values()].filter((v) => v.container === c.id).sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    if (views.length) containers.push({ id: c.id, title: c.title, location: c.location, order: c.order, views: views.map((v) => ({ id: v.id, title: viewTitle(v), collapsed: !!v.collapsed })) });
  }
  return { containers };
}

const containerTitle = (id) => containerSpecs.get(id)?.title ?? layout.custom[id]?.title ?? id;
const containerIcon = (id) => containerSpecs.get(id)?.icon ?? viewSpecs.get(layout.containers[id]?.views[0])?.icon ?? "window";
const viewsOf = (id) => (layout.containers[id]?.views ?? []).filter((v) => viewSpecs.has(v));
// The containers of a place that have an icon (or a tab): those with a view that exists, minus the ones taken off.
const shownContainers = (where) => layout.locations[where].order.filter((id) => viewsOf(id).length && !layout.hidden[id]);
const effective = () => layoutEffective(layout);

function setLayout(next) {
  if (!next || next === layout) return;
  layout = next;
  store.set(LAYOUT_KEY, layout);
  renderWorkbench();
}

function initLayout() {
  layout = layoutReconcile(store.get(LAYOUT_KEY), modelRegistry());
  buildPartSkeletons();
  wireSashes();
  wireDropTargets();
  renderWorkbench();
  window.addEventListener("resize", () => bus.emit("fit"));
}

// ------------------------------------------------------------------ what is on the page

const PANEL_POSITIONS_ALL = ["bottom", "left", "right"];

// Replaces the children of `host` unless its signature says they would come out the same: the page draws again every second while a run
// is going, and a click must not land on a button that was just rebuilt, nor a drag lose the icon it holds.
function setIfChanged(host, signature, make) {
  if (host.dataset.sig === signature) return;
  host.dataset.sig = signature;
  host.replaceChildren(...make());
}

const actionsSignature = (viewIds) => viewIds.flatMap((v) => (viewSpecs.get(v)?.actions?.() ?? []).filter((a) => !a.hidden).map((a) => `${a.icon}:${a.title}:${!!a.disabled}`)).join("|");
bus.on("bindings", () => { for (const el of $$("[data-sig]")) delete el.dataset.sig; });

function renderWorkbench() {
  const eff = effective();
  const body = document.body;
  body.classList.toggle("sidebar-right", eff.sidebarSide === "right");
  for (const p of PANEL_POSITIONS_ALL) body.classList.toggle(`panel-${p}`, eff.locations.panel.position === p);
  body.classList.toggle("panel-maximized", eff.locations.panel.visible && eff.locations.panel.maximized);
  body.classList.toggle("no-activitybar", !eff.activityBar);
  body.classList.toggle("no-statusbar", !eff.statusBar);
  body.classList.toggle("no-titlebar", !eff.titleBar);
  body.classList.toggle("zen", layout.zen);
  const root = document.documentElement.style;
  root.setProperty("--sidebar-w", `${eff.locations.sidebar.size}px`);
  root.setProperty("--secondary-w", `${eff.locations.secondary.size}px`);
  root.setProperty("--panel-size", `${eff.locations.panel.size}px`);
  $("#sidebar").hidden = !eff.locations.sidebar.visible;
  $("#secondary").hidden = !eff.locations.secondary.visible;
  $("#panel").hidden = !eff.locations.panel.visible;
  $("#sash-sidebar").hidden = !eff.locations.sidebar.visible;
  $("#sash-secondary").hidden = !eff.locations.secondary.visible;
  $("#sash-panel").hidden = !eff.locations.panel.visible || eff.locations.panel.maximized;
  renderActivityBar();
  renderSidePart("sidebar");
  renderSidePart("secondary");
  renderPanelPart();
  bus.emit("layout", layout);
  bus.emit("fit");
}

function buildPartSkeletons() {
  for (const where of ["sidebar", "secondary"]) {
    $(`#${where}`).replaceChildren(
      h("div", { class: "part-header" }, h("div", { class: "part-title" }), h("div", { class: "part-actions" })),
      h("div", { class: "part-content" }));
  }
  $("#panel").replaceChildren(
    h("div", { class: "part-header panel-header" }, h("div", { class: "panel-tabs", role: "tablist" }), h("div", { class: "part-actions" })),
    h("div", { class: "part-content" }));
}

// ------------------------------------------------------------------ the activity bar

function renderActivityBar() {
  if (dragged) { refreshPending = true; return; }                              // (an icon being dragged must not be replaced under the pointer)
  const bar = $("#activitybar");
  const eff = effective();
  const loc = eff.locations.sidebar;
  const ids = shownContainers("sidebar");
  const signature = JSON.stringify([ids, loc.visible, loc.active, ids.map((id) => containerSpecs.get(id)?.badge?.() ?? 0), ids.map(containerTitle), ids.map(containerIcon)]);
  if (bar.dataset.sig === signature) return;
  bar.dataset.sig = signature;
  const items = ids.map((id) => {
    const active = loc.visible && loc.active === id;
    const badge = containerSpecs.get(id)?.badge?.();
    return h("button", {
      class: `activity-item ${active ? "active" : ""}`, role: "tab", "aria-selected": String(active), title: `${containerTitle(id)}${containerKey(id)}`,
      "aria-label": containerTitle(id), draggable: "true", "data-container": id,
      onclick: () => toggleContainer(id),
      oncontextmenu: (ev) => { ev.preventDefault(); showContextMenu(ev, activityMenu(id)); },
      ondragstart: (ev) => startDrag(ev, "container", id),
      ondragend: endDrag,
      onkeydown: (ev) => moveFocusInBar(ev),
    }, icon(containerIcon(id), 24), badge ? h("span", { class: "activity-badge" }, String(badge)) : null);
  });
  const bottom = [
    h("button", { class: "activity-item", title: "Manage", "aria-label": "Manage", id: "manage-button", onclick: (ev) => showMenuAt(ev.currentTarget, manageMenu(), "up") }, icon("gear", 24)),
  ];
  bar.replaceChildren(
    h("div", { class: "activity-top", role: "tablist", "aria-orientation": "vertical" }, items),
    h("div", { class: "activity-bottom" }, bottom));
}

const containerKey = (id) => {
  const k = { explorer: "workbench.view.explorer", search: "workbench.action.findInFiles", scm: "workbench.view.scm", run: "workbench.view.run" }[id];
  const label = k ? keyLabel(k) : "";
  return label ? ` (${label})` : "";
};

function moveFocusInBar(ev) {
  if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
  const items = $$(".activity-top .activity-item");
  const at = items.indexOf(ev.currentTarget);
  const next = items[(at + (ev.key === "ArrowDown" ? 1 : -1) + items.length) % items.length];
  if (next) { ev.preventDefault(); next.focus(); }
}

// A click on the container on show hides the side bar; a click on another one shows that one (as in VS Code).
function toggleContainer(id) {
  const where = locationOf(layout, id);
  if (!where) return;
  const loc = layout.locations[where];
  if (loc.visible && loc.active === id) setLayout(layoutToggle(layout, where, false));
  else setLayout(layoutReveal(layout, id));
}

// A check for each container of a place: ticked when its icon (or tab) is there; a click takes it off or brings it back.
function visibilityItems(where) {
  return layout.locations[where].order.filter((c) => viewsOf(c).length).map((c) => ({
    label: containerTitle(c), checked: !layout.hidden[c], disabled: !layout.hidden[c] && shownContainers(where).length < 2,
    run: () => setLayout(layoutSetContainerHidden(layout, c, !layout.hidden[c])),
  }));
}

function activityMenu(id) {
  const where = locationOf(layout, id);
  return [
    ...visibilityItems("sidebar"),
    "-",
    ...moveContainerItems(id, where),
    "-",
    { label: "Reset View Locations", run: () => runCommand("workbench.action.resetViewLocations") },
    { label: "Hide Activity Bar", run: () => setLayout(layoutSet(layout, "activityBar", false)) },
  ];
}

function moveContainerItems(id, where) {
  const names = { sidebar: "Side Bar", secondary: "Secondary Side Bar", panel: "Panel" };
  return ["sidebar", "secondary", "panel"].filter((w) => w !== where).map((w) => ({ label: `Move to ${names[w]}`, run: () => setLayout(layoutMoveContainer(layout, id, w)) }));
}

// ------------------------------------------------------------------ the side bars

function renderSidePart(where) {
  const part = $(`#${where}`);
  const loc = layout.locations[where];
  const containers = shownContainers(where);
  const id = loc.active && viewsOf(loc.active).length ? loc.active : containers[0] ?? null;
  const title = $(".part-title", part);
  const actions = $(".part-actions", part);
  const content = $(".part-content", part);
  const ids = id ? viewsOf(id) : [];
  const single = ids.length === 1;

  const heading = where === "secondary" && containers.length > 1 ? containers.map(containerTitle) : id ? [single ? viewTitle(viewSpecs.get(ids[0])) : containerTitle(id)] : [];
  setIfChanged(title, JSON.stringify([id, containers, heading]), () => (where === "secondary" && containers.length > 1
    ? containers.map((c) => h("button", {
      class: `secondary-tab ${c === id ? "active" : ""}`, title: containerTitle(c), "data-container": c, draggable: "true",
      onclick: () => setLayout(layoutSetActive(layout, "secondary", c)), ondragstart: (ev) => startDrag(ev, "container", c), ondragend: endDrag,
    }, icon(containerIcon(c), 16)))
    : [id ? h("span", { draggable: "true", "data-container": id, ondragstart: (ev) => startDrag(ev, "container", id), ondragend: endDrag }, heading[0]) : ""]));
  setIfChanged(actions, JSON.stringify([id, single ? actionsSignature(ids) : ""]), () => [...(single ? viewActionButtons(ids[0]) : []),
    id ? iconButton("more", "Views and More Actions...", (ev) => showMenuAt(ev.currentTarget, partMenu(where, id))) : ""]);

  const sections = ids.map((vid) => paneFor(vid).el);
  if (!id) {
    content.replaceChildren(h("div", { class: "empty-part" }, where === "secondary"
      ? "Drag a view here to display it. Try the Outline, or a tab of the panel."
      : "Nothing to show here."));
    return;
  }
  const same = sections.length === content.children.length && sections.every((el, i) => content.children[i] === el);
  if (!same) swapChildren(content, sections);
  ids.forEach((vid, i) => {
    const pane = paneFor(vid);
    const collapsed = !!layout.views[vid]?.collapsed && !single;
    pane.el.classList.toggle("collapsed", collapsed);
    pane.el.classList.toggle("single", single);
    pane.header.setAttribute("aria-expanded", String(!collapsed));
    $(".pane-chevron", pane.header).replaceChildren(icon(collapsed ? "chevron-right" : "chevron-down", 16));
    if (!collapsed) ensureBuilt(vid);
    setIfChanged(pane.actions, single ? "single" : actionsSignature([vid]), () => (single ? [] : viewActionButtons(vid)));
    const heading = $(".pane-title", pane.header);
    if (heading.textContent !== viewTitle(viewSpecs.get(vid))) heading.textContent = viewTitle(viewSpecs.get(vid));
  });
}

// Children changed, but each keeps the place it was scrolled to.
function swapChildren(host, children) {
  const saved = new Map();
  for (const el of [...host.children, ...children]) for (const s of [el, ...$$("*", el)]) if (s.scrollTop || s.scrollLeft) saved.set(s, [s.scrollTop, s.scrollLeft]);
  host.replaceChildren(...children);
  for (const [el, [top, left]] of saved) { el.scrollTop = top; el.scrollLeft = left; }
}

function iconButton(name, title, onclick, { disabled = false, cls = "" } = {}) {
  return h("button", { class: `icon-button ${cls}`, title, "aria-label": title, disabled: disabled || null, onclick }, icon(name, 16));
}

function viewActionButtons(viewId) {
  const spec = viewSpecs.get(viewId);
  return (spec?.actions?.() ?? []).filter((a) => !a.hidden).map((a) => iconButton(a.icon, a.title, (ev) => { ev.stopPropagation(); a.run(ev); }, { disabled: a.disabled }));
}

function paneFor(viewId) {
  if (panes.has(viewId)) return panes.get(viewId);
  const spec = viewSpecs.get(viewId);
  const body = h("div", { class: "pane-body" });
  const actions = h("div", { class: "pane-actions" });
  const header = h("div", {
    class: "pane-header", role: "button", tabindex: "0", draggable: "true", "data-view": viewId, "aria-expanded": "true",
    onclick: () => setLayout(layoutToggleCollapsed(layout, viewId)),
    onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setLayout(layoutToggleCollapsed(layout, viewId)); } },
    oncontextmenu: (ev) => { ev.preventDefault(); showContextMenu(ev, viewMenu(viewId)); },
    ondragstart: (ev) => startDrag(ev, "view", viewId),
    ondragend: endDrag,
  }, h("span", { class: "pane-chevron" }), h("span", { class: "pane-title" }, viewTitle(spec)), actions);
  const el = h("section", { class: "pane", "data-view": viewId }, header, body);
  const pane = { el, header, body, actions, built: false };
  panes.set(viewId, pane);
  return pane;
}

function ensureBuilt(viewId) {
  const pane = paneFor(viewId);
  if (pane.built) return;
  pane.built = true;
  try { viewSpecs.get(viewId).create(pane.body, { refreshActions: () => refreshViewActions(viewId) }); viewSpecs.get(viewId).refresh?.(); } catch (err) { console.error(`view ${viewId}:`, err); pane.body.replaceChildren(h("p", { class: "hint" }, `This view failed to load: ${err.message}`)); }
}

function viewIsVisible(viewId) {
  const where = locationOf(layout, containerOfView(layout, viewId));
  if (!where) return false;
  const loc = effective().locations[where];
  const cid = containerOfView(layout, viewId);
  return loc.visible && loc.active === cid && !(layout.views[viewId]?.collapsed && viewsOf(cid).length > 1);
}

function refreshViewActions(viewId) {
  const where = locationOf(layout, containerOfView(layout, viewId));
  if (where === "panel") renderPanelPart();
  else if (where) renderSidePart(where);
}

// New data: every view that can be seen draws itself again (the others do when they are shown).
let refreshPending = false;

function refreshViews() {
  if (dragged || draggedTab) { refreshPending = true; return; }                 // (drawing the bars again would drop what the user holds)
  refreshPending = false;
  for (const [viewId, pane] of panes) {
    if (pane.built && viewIsVisible(viewId)) {
      try { viewSpecs.get(viewId).refresh?.(); } catch (err) { console.error(`view ${viewId}:`, err); }
    }
  }
  renderActivityBar();
  renderSidePart("sidebar");
  renderSidePart("secondary");
  renderPanelPart();
  bus.emit("views");
}

function viewMenu(viewId) {
  const cid = containerOfView(layout, viewId);
  const where = locationOf(layout, cid);
  const names = { sidebar: "Side Bar", secondary: "Secondary Side Bar", panel: "Panel" };
  const spec = viewSpecs.get(viewId);
  return [
    { label: layout.views[viewId]?.collapsed ? "Expand" : "Collapse", run: () => setLayout(layoutToggleCollapsed(layout, viewId)) },
    "-",
    ...["sidebar", "secondary", "panel"].map((w) => ({ label: `Move View to ${names[w]}`, disabled: w === where && viewsOf(cid).length === 1, run: () => setLayout(layoutViewToNewContainer(layout, viewId, w, viewTitle(spec))) })),
    "-",
    { label: "Reset Location", run: () => resetViewLocation(viewId) },
  ];
}

function resetViewLocation(viewId) {
  const home = viewSpecs.get(viewId).container;
  if (!layout.containers[home] && !containerSpecs.has(home)) return;
  let next = layout;
  if (!next.containers[home]) {                                         // its own container was emptied and removed: it comes back
    const defaults = layoutDefault(modelRegistry());
    next = clone(next);
    next.containers[home] = { views: [] };
    const where = containerSpecs.get(home).location;
    next.locations[where].order.push(home);
    next.views = { ...defaults.views, ...next.views };
  }
  setLayout(layoutMoveView(next, viewId, home));
}

function partMenu(where, id) {
  return [
    ...viewsOf(id).map((v) => ({ label: viewTitle(viewSpecs.get(v)), checked: !layout.views[v]?.collapsed, run: () => setLayout(layoutToggleCollapsed(layout, v)) })),
    "-",
    ...moveContainerItems(id, where),
    "-",
    { label: "Reset View Locations", run: () => runCommand("workbench.action.resetViewLocations") },
  ];
}

// ------------------------------------------------------------------ the panel

function renderPanelPart() {
  const part = $("#panel");
  const loc = layout.locations.panel;
  const containers = shownContainers("panel");
  const id = loc.active && viewsOf(loc.active).length ? loc.active : containers[0] ?? null;
  renderPanelTabsOnly();
  const actions = $(".part-header .part-actions", part);
  const maximized = loc.maximized;
  setIfChanged(actions, JSON.stringify([id, maximized, id ? actionsSignature(viewsOf(id)) : ""]), () => [
    ...(id ? viewsOf(id).flatMap((v) => viewActionButtons(v)) : []),
    iconButton("more", "Views and More Actions...", (ev) => showMenuAt(ev.currentTarget, panelMenu())),
    iconButton(maximized ? "restore" : "maximize", maximized ? "Restore Panel Size" : "Maximize Panel Size", () => runCommand("workbench.action.toggleMaximizedPanel")),
    iconButton("x", "Hide Panel", () => setLayout(layoutToggle(layout, "panel", false)))]);
  const content = $(".part-content", part);
  const ids = id ? viewsOf(id) : [];
  if (!ids.length) { content.replaceChildren(h("div", { class: "empty-part" }, "Drag a view here to display it.")); return; }
  const sections = ids.map((vid) => paneFor(vid).el);
  const same = sections.length === content.children.length && sections.every((el, i) => content.children[i] === el);
  if (!same) swapChildren(content, sections);
  ids.forEach((vid) => { paneFor(vid).el.classList.remove("collapsed"); paneFor(vid).el.classList.add("single"); ensureBuilt(vid); });
  for (const vid of ids) { const heading = $(".pane-title", paneFor(vid).header); if (heading.textContent !== viewTitle(viewSpecs.get(vid))) heading.textContent = viewTitle(viewSpecs.get(vid)); }
}

function renderPanelTabsOnly() {
  if (dragged) { refreshPending = true; return; }
  const loc = layout.locations.panel;
  const containers = shownContainers("panel");
  const active = loc.active && viewsOf(loc.active).length ? loc.active : containers[0];
  const holder = $(".panel-tabs", $("#panel"));
  const signature = JSON.stringify([containers, active, containers.map((c) => containerSpecs.get(c)?.badge?.() ?? 0), containers.map(containerTitle)]);
  if (holder.dataset.sig === signature) return;
  holder.dataset.sig = signature;
  holder.replaceChildren(...containers.map((c) => {
    const badge = containerSpecs.get(c)?.badge?.();
    return h("button", {
      class: `panel-tab ${c === active ? "active" : ""}`, role: "tab", "aria-selected": String(c === active), "data-container": c, draggable: "true",
      onclick: () => setLayout(layoutSetActive(layout, "panel", c)),
      oncontextmenu: (ev) => { ev.preventDefault(); showContextMenu(ev, [...visibilityItems("panel"), "-", ...moveContainerItems(c, "panel"), "-", { label: "Reset View Locations", run: () => runCommand("workbench.action.resetViewLocations") }]); },
      ondragstart: (ev) => startDrag(ev, "container", c), ondragend: endDrag,
    }, containerTitle(c), badge ? h("span", { class: "tab-badge" }, String(badge)) : null);
  }));
}

function panelMenu() {
  const position = layout.locations.panel.position;
  return [
    ...["Bottom", "Left", "Right"].map((name) => ({ label: `Panel Position: ${name}`, checked: position === name.toLowerCase(), run: () => setLayout(layoutSetPanelPosition(layout, name.toLowerCase())) })),
    "-",
    { label: layout.locations.panel.maximized ? "Restore Panel Size" : "Maximize Panel Size", run: () => runCommand("workbench.action.toggleMaximizedPanel") },
    { label: "Hide Panel", run: () => setLayout(layoutToggle(layout, "panel", false)) },
    "-",
    { label: "Reset View Locations", run: () => runCommand("workbench.action.resetViewLocations") },
  ];
}

// ------------------------------------------------------------------ dragging a container or a view to another place

let dragged = null;   // { kind: "container" | "view", id }

function startDrag(ev, kind, id) {
  dragged = { kind, id };
  ev.dataTransfer.effectAllowed = "move";
  ev.dataTransfer.setData("application/x-verdict-workbench", `${kind}:${id}`);
  document.body.classList.add("dragging-workbench");
  ev.stopPropagation();
}

function endDrag() {
  dragged = null;
  document.body.classList.remove("dragging-workbench");
  for (const el of $$(".drop-target, .drop-before, .drop-after")) el.classList.remove("drop-target", "drop-before", "drop-after");
  if (refreshPending) refreshViews();
}

// Where in a row of items (by their rectangles) a pointer is: the index to insert at.
function insertionIndex(items, ev, axis) {
  for (let i = 0; i < items.length; i++) {
    const box = items[i].getBoundingClientRect();
    const mid = axis === "y" ? box.top + box.height / 2 : box.left + box.width / 2;
    if ((axis === "y" ? ev.clientY : ev.clientX) < mid) return i;
  }
  return items.length;
}

function dropHere(ev, where, index = null) {
  if (!dragged) return;
  ev.preventDefault();
  ev.stopPropagation();
  const { kind, id } = dragged;
  endDrag();
  if (kind === "container") setLayout(layoutMoveContainer(layout, id, where, index));
  else setLayout(layoutViewToNewContainer(layout, id, where, viewSpecs.get(id) ? viewTitle(viewSpecs.get(id)) : id, index));
}

function wireDropTargets() {
  const accept = (el, mark = true) => (ev) => {
    if (!dragged) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    if (mark) el.classList.add("drop-target");
  };
  const leave = (el) => () => el.classList.remove("drop-target");
  // the activity bar: a container (or a view, which becomes one) goes between the icons
  const bar = $("#activitybar");
  const clearMarks = () => { for (const el of $$(".activity-item.drop-before, .activity-item.drop-after", bar)) el.classList.remove("drop-before", "drop-after"); };
  bar.addEventListener("dragover", (ev) => {
    accept(bar)(ev);
    if (!dragged) return;
    const items = $$(".activity-top .activity-item", bar);
    clearMarks();                                                                        // (a line shows between the icons where it would land)
    const at = insertionIndex(items, ev, "y");
    if (at < items.length) items[at].classList.add("drop-before"); else items[items.length - 1]?.classList.add("drop-after");
  });
  bar.addEventListener("dragleave", (ev) => { if (!bar.contains(ev.relatedTarget)) { leave(bar)(); clearMarks(); } });
  bar.addEventListener("drop", (ev) => dropHere(ev, "sidebar", insertionIndex($$(".activity-top .activity-item", bar), ev, "y")));
  // the side bars and the panel: dropped anywhere on them, a container lands there; on a pane header, a view lands before or after that pane
  for (const where of ["sidebar", "secondary", "panel"]) {
    const part = $(`#${where}`);
    part.addEventListener("dragover", accept(part));
    part.addEventListener("dragleave", (ev) => { if (!part.contains(ev.relatedTarget)) part.classList.remove("drop-target"); });
    part.addEventListener("drop", (ev) => {
      if (!dragged) return;
      const header = ev.target.closest?.(".pane-header");
      if (dragged.kind === "view" && header && where !== "panel") {
        const target = header.dataset.view;
        const container = containerOfView(layout, target);
        const views = layout.containers[container].views;
        const box = header.getBoundingClientRect();
        const at = views.indexOf(target) + (ev.clientY >= box.top + box.height / 2 ? 1 : 0);
        const id = dragged.id;
        endDrag();
        ev.preventDefault();
        ev.stopPropagation();
        setLayout(layoutMoveView(layout, id, container, at));
        return;
      }
      if (dragged.kind === "view" && where !== "panel" && !$(".part-header", part).contains(ev.target)) {
        const container = layout.locations[where].active;
        if (container) { const id = dragged.id; endDrag(); ev.preventDefault(); ev.stopPropagation(); setLayout(layoutMoveView(layout, id, container)); return; }
      }
      const tabs = $$(".panel-tab, .secondary-tab", part);
      dropHere(ev, where, where === "sidebar" ? null : tabs.length ? insertionIndex(tabs, ev, "x") : null);
    });
  }
}

// ------------------------------------------------------------------ the dividers

function wireSashes() {
  dragSash($("#sash-sidebar"), (ev) => {
    const bar = effective().activityBar ? $("#activitybar").getBoundingClientRect().width : 0;
    const size = layout.sidebarSide === "left" ? ev.clientX - bar : window.innerWidth - ev.clientX - bar;
    return layoutResize(layout, "sidebar", size);
  }, () => setLayout(layoutResize(layout, "sidebar", 300)));
  dragSash($("#sash-secondary"), (ev) => {
    const size = layout.sidebarSide === "left" ? window.innerWidth - ev.clientX : ev.clientX;
    return layoutResize(layout, "secondary", size);
  }, () => setLayout(layoutResize(layout, "secondary", 300)));
  dragSash($("#sash-panel"), (ev) => {
    const box = $("#center").getBoundingClientRect();
    const position = layout.locations.panel.position;
    const size = position === "bottom" ? box.bottom - ev.clientY : position === "left" ? ev.clientX - box.left : box.right - ev.clientX;
    return layoutResize(layout, "panel", size);
  }, () => setLayout(layoutResize(layout, "panel", 280)));
}

// A divider you drag with the mouse, move with the arrow keys, or double click to give back its usual size.
function dragSash(sash, resized, reset) {
  sash.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    sash.setPointerCapture?.(ev.pointerId);
    sash.classList.add("active");
    document.body.classList.add("resizing");
    const move = (e) => { const next = resized(e); if (next !== layout) { layout = next; renderSizesOnly(); } };
    sash.addEventListener("pointermove", move);
    sash.addEventListener("lostpointercapture", () => {
      sash.removeEventListener("pointermove", move);
      sash.classList.remove("active");
      document.body.classList.remove("resizing");
      store.set(LAYOUT_KEY, layout);
      bus.emit("fit");
    }, { once: true });
  });
  sash.addEventListener("dblclick", reset);
  sash.addEventListener("keydown", (ev) => {
    const step = { ArrowLeft: -16, ArrowUp: -16, ArrowRight: 16, ArrowDown: 16 }[ev.key];
    if (!step) return;
    ev.preventDefault();
    const where = sash.id === "sash-sidebar" ? "sidebar" : sash.id === "sash-secondary" ? "secondary" : "panel";
    const grows = (where === "sidebar" && layout.sidebarSide === "left") || (where === "secondary" && layout.sidebarSide === "right") || (where === "panel" && layout.locations.panel.position === "left");
    const delta = where === "panel" && layout.locations.panel.position === "bottom" ? -step : grows ? step : -step;
    setLayout(layoutResize(layout, where, layout.locations[where].size + delta));
  });
}

function renderSizesOnly() {
  const root = document.documentElement.style;
  const eff = effective();
  root.setProperty("--sidebar-w", `${eff.locations.sidebar.size}px`);
  root.setProperty("--secondary-w", `${eff.locations.secondary.size}px`);
  root.setProperty("--panel-size", `${eff.locations.panel.size}px`);
  bus.emit("fit");
}
