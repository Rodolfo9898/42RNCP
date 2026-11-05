"use strict";

// The pure models behind the workbench: where each view lives (side bar, secondary side bar, panel), how editor groups and terminal panes
// are split, how keys, settings, find, outline and diff behave. No DOM here: Node loads this file too (see the bottom), which is how it is
// tested. Everything takes plain data and returns new plain data; nothing is changed in place.

const clone = (value) => JSON.parse(JSON.stringify(value));

// ------------------------------------------------------------------ a grid of leaves: editor groups and terminal panes are split the same way
// A node is {leaf: id} or {dir: "row" | "column", children: [node...], sizes: [weight...]}; a row puts its children side by side.

const gridIsLeaf = (node) => node != null && node.leaf !== undefined;
const gridAxis = (side) => (side === "left" || side === "right" ? "row" : "column");

function gridLeaves(node) {
  return !node ? [] : gridIsLeaf(node) ? [node.leaf] : node.children.flatMap(gridLeaves);
}

// A new leaf next to `id`, on the given side ("left" | "right" | "up" | "down"). It takes half of the room of `id`.
function gridSplit(node, id, side, newId) {
  const before = side === "left" || side === "up";
  const dir = gridAxis(side);
  const walk = (n) => {
    if (gridIsLeaf(n)) return n.leaf !== id ? n : { dir, children: before ? [{ leaf: newId }, n] : [n, { leaf: newId }], sizes: [1, 1] };
    const at = n.children.findIndex((c) => gridIsLeaf(c) && c.leaf === id);
    if (at >= 0 && n.dir === dir) {
      const children = n.children.slice(), sizes = n.sizes.slice();
      const half = sizes[at] / 2;
      sizes[at] = half;
      children.splice(before ? at : at + 1, 0, { leaf: newId });
      sizes.splice(before ? at : at + 1, 0, half);
      return { dir, children, sizes };
    }
    return { dir: n.dir, children: n.children.map(walk), sizes: n.sizes.slice() };
  };
  return node ? walk(node) : { leaf: newId };
}

// Without `id`. What is left takes the room; a split with one child becomes that child; a split inside a split of the same direction merges.
function gridRemove(node, id) {
  const walk = (n) => {
    if (gridIsLeaf(n)) return n.leaf === id ? null : n;
    const kept = [], weights = [];
    n.children.forEach((c, i) => { const r = walk(c); if (r) { kept.push(r); weights.push(n.sizes[i]); } });
    if (!kept.length) return null;
    if (kept.length === 1) return kept[0];
    const children = [], sizes = [];
    kept.forEach((c, i) => {
      if (!gridIsLeaf(c) && c.dir === n.dir) {
        const total = c.sizes.reduce((a, b) => a + b, 0) || 1;
        c.children.forEach((g, j) => { children.push(g); sizes.push(weights[i] * c.sizes[j] / total); });
      } else { children.push(c); sizes.push(weights[i]); }
    });
    return { dir: n.dir, children, sizes };
  };
  return node ? walk(node) : null;
}

// The leaf you reach from `id` going "left" | "right" | "up" | "down", or null.
function gridNeighbor(node, id, direction) {
  const axis = gridAxis(direction), forward = direction === "right" || direction === "down";
  const path = [];
  const find = (n) => {
    if (gridIsLeaf(n)) return n.leaf === id;
    for (let i = 0; i < n.children.length; i++) {
      path.push([n, i]);
      if (find(n.children[i])) return true;
      path.pop();
    }
    return false;
  };
  if (!node || !find(node)) return null;
  for (let k = path.length - 1; k >= 0; k--) {
    const [parent, i] = path[k];
    const j = forward ? i + 1 : i - 1;
    if (parent.dir !== axis || j < 0 || j >= parent.children.length) continue;
    let cur = parent.children[j];
    while (!gridIsLeaf(cur)) cur = cur.dir === axis ? cur.children[forward ? 0 : cur.children.length - 1] : cur.children[0];
    return cur.leaf;
  }
  return null;
}

// The weights of the split reached by `path` (child indexes from the root), e.g. after a divider was dragged.
function gridSetSizes(node, path, sizes) {
  const next = clone(node);
  let cur = next;
  for (const i of path) cur = cur && cur.children ? cur.children[i] : null;
  if (cur && cur.children && sizes.length === cur.children.length && sizes.every((s) => Number.isFinite(s) && s > 0)) cur.sizes = sizes.slice();
  return next;
}

function gridEqualize(node) {
  if (!node || gridIsLeaf(node)) return node;
  return { dir: node.dir, children: node.children.map(gridEqualize), sizes: node.children.map(() => 1) };
}

// ------------------------------------------------------------------ the layout: which container is in the side bar, the secondary side bar or the panel
// registry: { containers: [{ id, title, location, order?, views: [{ id, title, collapsed? }] }] }. The layout keeps only where things are.

const LOCATIONS = ["sidebar", "secondary", "panel"];
const SIZE_LIMITS = { sidebar: [170, 900], secondary: [170, 900], panel: [80, 1400] };
const PANEL_POSITIONS = ["bottom", "left", "right"];

function layoutDefault(registry) {
  const layout = {
    v: 2, sidebarSide: "left", activityBar: true, statusBar: true, titleBar: true, breadcrumbs: true, minimap: true, zen: false,
    locations: {
      sidebar: { order: [], active: null, visible: true, size: 300 },
      secondary: { order: [], active: null, visible: false, size: 300 },
      panel: { order: [], active: null, visible: true, size: 280, position: "bottom", maximized: false },
    },
    containers: {}, views: {}, custom: {}, hidden: {},
  };
  const known = [...registry.containers].sort((a, b) => (a.order ?? 100) - (b.order ?? 100));
  for (const c of known) {
    layout.locations[c.location].order.push(c.id);
    layout.containers[c.id] = { views: c.views.map((v) => v.id) };
    for (const v of c.views) layout.views[v.id] = { collapsed: !!v.collapsed };
  }
  for (const where of LOCATIONS) layout.locations[where].active = layout.locations[where].order[0] ?? null;
  return layout;
}

const isRecord = (x) => x != null && typeof x === "object" && !Array.isArray(x);
const clampSize = (where, value, fallback) => {
  const [low, high] = SIZE_LIMITS[where];
  return Number.isFinite(value) ? Math.round(Math.min(Math.max(value, low), high)) : fallback;
};

// What was saved (it may come from an older version, or be garbage) made valid for the views that exist now: every view in one container,
// every container in one place, nothing unknown, nothing empty.
function layoutReconcile(saved, registry) {
  const base = layoutDefault(registry);
  if (!isRecord(saved) || saved.v !== 2) return base;
  const out = clone(base);
  for (const key of ["activityBar", "statusBar", "titleBar", "breadcrumbs", "minimap", "zen"]) if (typeof saved[key] === "boolean") out[key] = saved[key];
  if (saved.sidebarSide === "left" || saved.sidebarSide === "right") out.sidebarSide = saved.sidebarSide;

  const viewTitle = new Map(registry.containers.flatMap((c) => c.views.map((v) => [v.id, v.title])));
  const builtin = new Map(registry.containers.map((c) => [c.id, c]));
  const custom = isRecord(saved.custom) ? saved.custom : {};
  const savedContainers = isRecord(saved.containers) ? saved.containers : {};

  // which views each container holds now
  const placed = new Set();
  const containers = {};
  const ids = [...builtin.keys(), ...Object.keys(custom).filter((id) => !builtin.has(id) && typeof custom[id]?.title === "string")];
  for (const id of ids) {
    const asked = Array.isArray(savedContainers[id]?.views) ? savedContainers[id].views : base.containers[id]?.views ?? [];
    const views = [];
    for (const v of asked) if (typeof v === "string" && viewTitle.has(v) && !placed.has(v)) { views.push(v); placed.add(v); }          // (once only)
    containers[id] = { views };
  }
  for (const c of registry.containers) for (const v of c.views) {                       // a view nobody holds yet: back in its own container
    if (!placed.has(v.id)) { containers[c.id].views.push(v.id); placed.add(v.id); }
  }
  out.custom = {};
  for (const id of ids) if (!builtin.has(id) && containers[id].views.length) out.custom[id] = { title: String(custom[id].title).slice(0, 60) };
  out.containers = {};
  for (const id of ids) if (containers[id].views.length) out.containers[id] = containers[id];

  // where each container lives
  const seen = new Set();
  for (const where of LOCATIONS) {
    const loc = isRecord(saved.locations?.[where]) ? saved.locations[where] : {};
    const order = (Array.isArray(loc.order) ? loc.order : []).filter((id) => typeof id === "string" && out.containers[id] && !seen.has(id));
    order.forEach((id) => seen.add(id));
    out.locations[where].order = order;
    if (typeof loc.visible === "boolean") out.locations[where].visible = loc.visible;
    out.locations[where].size = clampSize(where, loc.size, base.locations[where].size);
    out.locations[where].active = order.includes(loc.active) ? loc.active : order[0] ?? null;
    if (where === "panel") {
      if (PANEL_POSITIONS.includes(loc.position)) out.locations.panel.position = loc.position;
      if (typeof loc.maximized === "boolean") out.locations.panel.maximized = loc.maximized;
    }
  }
  for (const id of Object.keys(out.containers)) {                                         // a container nobody placed: where it was born, else the side bar
    if (seen.has(id)) continue;
    const where = builtin.get(id)?.location ?? "sidebar";
    out.locations[where].order.push(id);
    if (!out.locations[where].active) out.locations[where].active = id;
  }
  // icons taken off the activity bar (or tabs off the panel): a place always keeps at least one, and the one on show is never hidden
  out.hidden = {};
  if (isRecord(saved.hidden)) for (const id of Object.keys(saved.hidden)) if (saved.hidden[id] === true && out.containers[id]) out.hidden[id] = true;
  for (const where of LOCATIONS) {
    const loc = out.locations[where];
    const open = loc.order.filter((id) => !out.hidden[id]);
    if (loc.order.length && !open.length) delete out.hidden[loc.order[0]];
    if (out.hidden[loc.active]) loc.active = loc.order.find((id) => !out.hidden[id]) ?? null;
  }
  out.views = {};
  for (const id of placed) {
    const was = saved.views?.[id]?.collapsed;
    out.views[id] = { collapsed: typeof was === "boolean" ? was : !!base.views[id]?.collapsed };                 // (not saved: as the view starts)
  }
  return out;
}

const locationOf = (layout, containerId) => LOCATIONS.find((where) => layout.locations[where].order.includes(containerId)) ?? null;
const containerOfView = (layout, viewId) => Object.keys(layout.containers).find((id) => layout.containers[id].views.includes(viewId)) ?? null;

// A container is taken out of its place; the neighbour that was beside it becomes the one on show.
function detachContainer(layout, id) {
  const where = locationOf(layout, id);
  if (!where) return;
  const loc = layout.locations[where];
  const at = loc.order.indexOf(id);
  loc.order.splice(at, 1);
  if (loc.active === id) loc.active = loc.order[Math.min(at, loc.order.length - 1)] ?? null;
}

function layoutMoveContainer(layout, id, where, index = null) {
  if (!LOCATIONS.includes(where) || !layout.containers[id]) return layout;
  const next = clone(layout);
  detachContainer(next, id);
  const loc = next.locations[where];
  loc.order.splice(index === null ? loc.order.length : Math.max(0, Math.min(index, loc.order.length)), 0, id);
  loc.active = id;                                                                      // what you just dropped is what you see
  loc.visible = true;
  delete next.hidden[id];
  return next;
}

// A view into another container, before the view that is at `index` now (so dropping it on a header puts it before that view, in this
// container or another). A container left with nothing disappears from its place.
function layoutMoveView(layout, viewId, containerId, index = null) {
  const from = containerOfView(layout, viewId);
  if (!from || !layout.containers[containerId]) return layout;
  const next = clone(layout);
  const list = next.containers[from].views;
  const removedAt = list.indexOf(viewId);
  const before = next.containers[containerId].views.length;                             // (how many there were when the index was chosen)
  list.splice(removedAt, 1);
  const target = next.containers[containerId].views;
  const asked = index === null ? before : Math.max(0, Math.min(index, before));
  const to = from === containerId && removedAt < asked ? asked - 1 : asked;
  target.splice(Math.min(to, target.length), 0, viewId);
  if (!list.length && from !== containerId) removeContainer(next, from);
  const where = locationOf(next, containerId);
  if (where) { next.locations[where].active = containerId; next.locations[where].visible = true; }
  next.views[viewId] = { collapsed: false };
  return next;
}

function removeContainer(layout, id) {
  detachContainer(layout, id);
  delete layout.containers[id];
  delete layout.custom[id];
  delete layout.hidden[id];
}

// A view becomes a container of its own (dragged to the activity bar or to an empty part).
function layoutViewToNewContainer(layout, viewId, where, title, index = null) {
  const from = containerOfView(layout, viewId);
  if (!from || !LOCATIONS.includes(where)) return layout;
  if (layout.containers[from].views.length === 1 && locationOf(layout, from) !== where) return layoutMoveContainer(layout, from, where, index);   // already alone: the container moves
  if (layout.containers[from].views.length === 1) return layout;
  const next = clone(layout);
  const id = `custom-${viewId}`;
  const list = next.containers[from].views;
  list.splice(list.indexOf(viewId), 1);
  next.containers[id] = { views: [viewId] };
  next.custom[id] = { title: String(title).slice(0, 60) };
  const loc = next.locations[where];
  loc.order.splice(index === null ? loc.order.length : Math.max(0, Math.min(index, loc.order.length)), 0, id);
  loc.active = id;
  loc.visible = true;
  next.views[viewId] = { collapsed: false };
  return next;
}

function layoutSetActive(layout, where, id) {
  if (!layout.locations[where]?.order.includes(id)) return layout;
  const next = clone(layout);
  next.locations[where].active = id;
  return next;
}

function layoutToggle(layout, where, visible = null) {
  const next = clone(layout);
  const loc = next.locations[where];
  loc.visible = visible === null ? !loc.visible : !!visible;
  if (where === "panel" && !loc.visible) loc.maximized = false;
  return next;
}

function layoutSetPanelPosition(layout, position) {
  if (!PANEL_POSITIONS.includes(position)) return layout;
  const next = clone(layout);
  next.locations.panel.position = position;
  return next;
}

function layoutResize(layout, where, size) {
  const next = clone(layout);
  next.locations[where].size = clampSize(where, size, layout.locations[where].size);
  return next;
}

// Make a container visible and in front, wherever it lives (the "Focus on … view" commands).
function layoutReveal(layout, containerId) {
  const where = locationOf(layout, containerId);
  if (!where) return layout;
  const next = clone(layout);
  next.locations[where].active = containerId;
  next.locations[where].visible = true;
  delete next.hidden[containerId];                                                      // (showing a view brings its icon back)
  return next;
}

// An icon taken off the activity bar, or a tab off the panel (the right click menu of both). It is still there: showing its view brings it
// back. The last icon of a place cannot be taken off, and the one on show gives way to its neighbour.
function layoutSetContainerHidden(layout, id, hidden) {
  const where = locationOf(layout, id);
  if (!where) return layout;
  const next = clone(layout);
  const loc = next.locations[where];
  if (!hidden) { delete next.hidden[id]; return next; }
  const others = loc.order.filter((c) => c !== id && !next.hidden[c]);
  if (!others.length) return layout;
  next.hidden[id] = true;
  if (loc.active === id) loc.active = loc.order.slice(loc.order.indexOf(id) + 1).find((c) => !next.hidden[c]) ?? others[0];
  return next;
}

function layoutRevealView(layout, viewId) {
  const id = containerOfView(layout, viewId);
  if (!id) return layout;
  const next = layoutReveal(layout, id);
  if (next.views[viewId]) next.views[viewId].collapsed = false;
  return next;
}

function layoutToggleCollapsed(layout, viewId, collapsed = null) {
  if (!layout.views[viewId]) return layout;
  const next = clone(layout);
  next.views[viewId].collapsed = collapsed === null ? !next.views[viewId].collapsed : !!collapsed;
  return next;
}

function layoutSet(layout, key, value) {
  const next = clone(layout);
  if (key === "sidebarSide") { if (value === "left" || value === "right") next.sidebarSide = value; }
  else if (key === "maximized") next.locations.panel.maximized = !!value && next.locations.panel.visible;
  else if (typeof next[key] === "boolean") next[key] = !!value;
  return next;
}

// The window as VS Code's Zen Mode shows it: nothing but the editor.
function layoutEffective(layout) {
  if (!layout.zen) return layout;
  const next = clone(layout);
  next.activityBar = next.statusBar = next.titleBar = false;
  for (const where of LOCATIONS) next.locations[where].visible = false;
  return next;
}

// ------------------------------------------------------------------ editor groups
// state: { grid, groups: { id: { tabs: [key], active, history: [key] } }, active: groupId, next: number }

function groupsNew() {
  return { grid: { leaf: "g1" }, groups: { g1: { tabs: [], active: null, history: [] } }, active: "g1", next: 2 };
}

function groupsGroupOf(state, key) {
  return Object.keys(state.groups).find((id) => state.groups[id].tabs.includes(key)) ?? null;
}

function groupsTouch(group, key) {
  group.active = key;
  group.history = group.history.filter((k) => k !== key).concat(key);
}

// Add a tab to a group (moving it when it is open in another one) and bring it to the front. `index`: where among the tabs.
function groupsOpen(state, key, groupId = null, index = null) {
  const next = clone(state);
  const target = groupId && next.groups[groupId] ? groupId : next.active;
  const from = groupsGroupOf(next, key);
  if (from === target) { groupsTouch(next.groups[target], key); next.active = target; return next; }
  if (from) removeTab(next, key);
  const group = next.groups[target];
  const at = index === null ? group.tabs.length : Math.max(0, Math.min(index, group.tabs.length));
  group.tabs.splice(at, 0, key);
  groupsTouch(group, key);
  next.active = target;
  return next;
}

// Take a tab out; the group shows the tab used most recently, else the one beside it. A group left empty goes (unless it is the last).
function removeTab(state, key) {
  const id = groupsGroupOf(state, key);
  if (!id) return;
  const group = state.groups[id];
  const at = group.tabs.indexOf(key);
  group.tabs.splice(at, 1);
  group.history = group.history.filter((k) => k !== key);
  if (group.active === key) group.active = group.history.filter((k) => group.tabs.includes(k)).pop() ?? group.tabs[Math.min(at, group.tabs.length - 1)] ?? null;
  if (!group.tabs.length && Object.keys(state.groups).length > 1) dropGroup(state, id);
}

function dropGroup(state, id) {
  const leaves = gridLeaves(state.grid);
  const at = leaves.indexOf(id);
  state.grid = gridRemove(state.grid, id);
  delete state.groups[id];
  if (state.active === id) {
    const rest = gridLeaves(state.grid);
    state.active = rest[Math.min(at, rest.length - 1)] ?? rest[0];
  }
}

function groupsCloseTab(state, key) {
  const next = clone(state);
  removeTab(next, key);
  return next;
}

// An empty group beside `groupId`; with `key`, that tab moves into it. Returns the new state and the id of the group.
function groupsSplit(state, groupId, side, key = null) {
  const next = clone(state);
  const source = next.groups[groupId] ? groupId : next.active;
  const id = `g${next.next++}`;
  next.grid = gridSplit(next.grid, source, side, id);
  next.groups[id] = { tabs: [], active: null, history: [] };
  next.active = id;
  if (key && groupsGroupOf(next, key)) {
    const from = groupsGroupOf(next, key);
    next.groups[from].tabs.splice(next.groups[from].tabs.indexOf(key), 1);
    next.groups[from].history = next.groups[from].history.filter((k) => k !== key);
    if (next.groups[from].active === key) next.groups[from].active = next.groups[from].history.filter((k) => next.groups[from].tabs.includes(k)).pop() ?? next.groups[from].tabs[0] ?? null;
    next.groups[id].tabs.push(key);
    groupsTouch(next.groups[id], key);
    if (!next.groups[from].tabs.length) dropGroup(next, from);
  }
  return { state: next, group: id };
}

// Close a group; the keys of its tabs are returned so that the caller can close them for real.
function groupsCloseGroup(state, groupId) {
  const next = clone(state);
  const keys = next.groups[groupId] ? next.groups[groupId].tabs.slice() : [];
  if (!next.groups[groupId]) return { state: next, closed: [] };
  if (Object.keys(next.groups).length > 1) dropGroup(next, groupId);
  else { next.groups[groupId] = { tabs: [], active: null, history: [] }; }
  return { state: next, closed: keys };
}

function groupsActivateGroup(state, groupId) {
  if (!state.groups[groupId] || state.active === groupId) return state;
  const next = clone(state);
  next.active = groupId;
  return next;
}

function groupsMoveWithin(state, key, to, after) {
  const id = groupsGroupOf(state, key);
  if (!id) return state;
  const next = clone(state);
  next.groups[id].tabs = moveKey(next.groups[id].tabs, key, to, after);
  return next;
}

function groupsFocusDirection(state, direction) {
  return gridNeighbor(state.grid, state.active, direction);
}

// The tabs in the order a person reads them: group after group.
function groupsAllTabs(state) {
  return gridLeaves(state.grid).flatMap((id) => state.groups[id].tabs);
}

// ------------------------------------------------------------------ terminals: groups of split panes
// state: { groups: [{ id, grid, active }], active: groupId, titles: { pane: title }, kinds: { pane: "shell"|"claude" }, nextGroup, nextPane }

function termNew() {
  return { groups: [], active: null, titles: {}, nextGroup: 1, nextPane: 1 };
}

const termGroupOf = (state, pane) => state.groups.find((g) => gridLeaves(g.grid).includes(pane))?.id ?? null;
const termPanes = (state) => state.groups.flatMap((g) => gridLeaves(g.grid));

// A new terminal in a group of its own. Returns the state and the name of the pane (t1, t2...: the terminal service keeps shells under it).
function termAdd(state, title = "") {
  const next = clone(state);
  const pane = `t${next.nextPane++}`;
  const id = `tg${next.nextGroup++}`;
  next.groups.push({ id, grid: { leaf: pane }, active: pane });
  next.active = id;
  next.titles[pane] = title || "zsh";
  return { state: next, pane };
}

// A new terminal beside `pane` in its group ("right" or "down" in the usual case).
function termSplit(state, pane, side = "right", title = "") {
  const gid = termGroupOf(state, pane);
  if (!gid) return termAdd(state, title);
  const next = clone(state);
  const group = next.groups.find((g) => g.id === gid);
  const fresh = `t${next.nextPane++}`;
  group.grid = gridSplit(group.grid, pane, side, fresh);
  group.active = fresh;
  next.active = gid;
  next.titles[fresh] = title || next.titles[pane] || "zsh";
  return { state: next, pane: fresh };
}

function termKill(state, pane) {
  const gid = termGroupOf(state, pane);
  if (!gid) return state;
  const next = clone(state);
  const at = next.groups.findIndex((g) => g.id === gid);
  const group = next.groups[at];
  const order = gridLeaves(group.grid);
  group.grid = gridRemove(group.grid, pane);
  delete next.titles[pane];
  if (!group.grid) {
    next.groups.splice(at, 1);
    if (next.active === gid) next.active = (next.groups[Math.min(at, next.groups.length - 1)] ?? null)?.id ?? null;
  } else if (group.active === pane) {
    const rest = gridLeaves(group.grid);
    group.active = rest[Math.min(order.indexOf(pane), rest.length - 1)];
  }
  return next;
}

function termFocus(state, pane) {
  const gid = termGroupOf(state, pane);
  if (!gid) return state;
  const next = clone(state);
  next.active = gid;
  next.groups.find((g) => g.id === gid).active = pane;
  return next;
}

function termRename(state, pane, title) {
  if (!(pane in state.titles) || !String(title).trim()) return state;
  const next = clone(state);
  next.titles[pane] = String(title).trim().slice(0, 40);
  return next;
}

// The pane you reach from the active one with Alt+Arrow.
function termFocusDirection(state, direction) {
  const group = state.groups.find((g) => g.id === state.active);
  return group ? gridNeighbor(group.grid, group.active, direction) : null;
}

function termActivePane(state) {
  return state.groups.find((g) => g.id === state.active)?.active ?? null;
}

// Terminals that run on the server and are not on the page (a reloaded page): one group each.
function termAdopt(state, panes) {
  let next = state;
  for (const pane of panes) {
    if (!pane || termGroupOf(next, pane)) continue;
    next = clone(next);
    const n = Number(pane.slice(1));
    if (/^t\d+$/.test(pane)) next.nextPane = Math.max(next.nextPane, n + 1);
    const id = `tg${next.nextGroup++}`;
    next.groups.push({ id, grid: { leaf: pane }, active: pane });
    next.titles[pane] = next.titles[pane] || "zsh";
    next.active ??= id;
  }
  return next;
}

// ------------------------------------------------------------------ settings

// schema: [{ id, type: "boolean" | "number" | "enum" | "string", default, min?, max?, options?: [value] }]
function normalizeSettings(raw, schema) {
  const out = {};
  for (const item of schema) {
    const value = isRecord(raw) ? raw[item.id] : undefined;
    let ok = false;
    if (item.type === "boolean") ok = typeof value === "boolean";
    else if (item.type === "number") ok = typeof value === "number" && Number.isFinite(value);
    else if (item.type === "enum") ok = item.options.includes(value);
    else if (item.type === "string") ok = typeof value === "string" && value.length <= (item.max ?? 200);
    out[item.id] = !ok ? item.default : item.type === "number" ? Math.min(Math.max(value, item.min ?? -Infinity), item.max ?? Infinity) : value;
  }
  return out;
}

// ------------------------------------------------------------------ keybindings
// A stroke is "mod+shift+p"; a chord is strokes separated by a space ("mod+k z"). "mod" is Cmd on a Mac and Ctrl elsewhere.

const MODIFIER_ORDER = ["mod", "meta", "ctrl", "alt", "shift"];             // (the order a binding is written in: mod+alt+b, ctrl+shift+`)
const KEY_ALIASES = { arrowleft: "left", arrowright: "right", arrowup: "up", arrowdown: "down", esc: "escape", return: "enter", del: "delete", " ": "space" };
const PUNCTUATION_CODES = { "`": "Backquote", "-": "Minus", "=": "Equal", "[": "BracketLeft", "]": "BracketRight", "\\": "Backslash", ";": "Semicolon", "'": "Quote", ",": "Comma", ".": "Period", "/": "Slash" };

function normalizeStroke(text) {
  const parts = String(text).trim().toLowerCase().split("+").map((p) => p.trim());
  let key = parts.pop();
  if (key === "" && parts.at(-1) === "") { parts.pop(); key = "+"; }                    // "ctrl++"
  key = KEY_ALIASES[key] ?? key;
  const names = { cmd: "mod", command: "mod", control: "ctrl", option: "alt", opt: "alt", win: "meta", super: "meta" };
  const mods = [...new Set(parts.filter(Boolean).map((m) => names[m] ?? m))].filter((m) => MODIFIER_ORDER.includes(m));
  mods.sort((a, b) => MODIFIER_ORDER.indexOf(a) - MODIFIER_ORDER.indexOf(b));
  return [...mods, key].join("+");
}

const normalizeChord = (text) => String(text).trim().split(/\s+/).filter(Boolean).map(normalizeStroke);

// The stroke an event is, in the form above (null for a modifier on its own).
function strokeFromEvent(ev, isMac) {
  const code = String(ev.code || ""), typed = String(ev.key || "");
  if (/^(Shift|Control|Alt|Meta|OS)$/.test(typed) || /^(Shift|Control|Alt|Meta|OS)(Left|Right)$/.test(code)) return null;
  let key;
  if (/^Key[A-Z]$/.test(code)) key = code.slice(3).toLowerCase();
  else if (/^Digit\d$/.test(code)) key = code.slice(5);
  else if (/^F\d{1,2}$/.test(typed)) key = typed.toLowerCase();
  else {
    const byCode = Object.entries(PUNCTUATION_CODES).find(([, c]) => c === code);
    key = byCode ? byCode[0] : (KEY_ALIASES[typed.toLowerCase()] ?? typed.toLowerCase());
  }
  if (!key) return null;
  const mods = [];
  if (ev.ctrlKey) mods.push(isMac ? "ctrl" : "mod");
  if (ev.altKey) mods.push("alt");
  if (ev.shiftKey) mods.push("shift");
  if (ev.metaKey) mods.push(isMac ? "mod" : "meta");
  return normalizeStroke([...mods, key].join("+"));
}

// defaults: [{ command, key, when? }]. overrides: [{ command, key, when? }]; a command starting with "-" takes that key away from the command.
// Returns [{ command, strokes: [stroke], when, source: "default" | "user" }], later ones winning for the same keys.
function resolveBindings(defaults, overrides) {
  let list = defaults.map((b) => ({ command: b.command, strokes: normalizeChord(b.key), when: b.when ?? "", source: "default" }));
  for (const o of Array.isArray(overrides) ? overrides : []) {
    if (!isRecord(o) || typeof o.command !== "string" || typeof o.key !== "string") continue;
    const strokes = normalizeChord(o.key);
    if (!strokes.length) continue;
    if (o.command.startsWith("-")) {
      const wanted = o.command.slice(1);
      list = list.filter((b) => !(b.command === wanted && b.strokes.join(" ") === strokes.join(" ")));
    } else list.push({ command: o.command, strokes, when: typeof o.when === "string" ? o.when : "", source: "user" });
  }
  return list;
}

// when: "editorFocus && !terminalFocus", "a || b", parentheses. A name is true when ctx[name] is. Anything unreadable is false.
function evalWhen(expr, ctx) {
  const tokens = String(expr ?? "").match(/&&|\|\||!|\(|\)|[\w.-]+/g) ?? [];
  let i = 0;
  const or = () => { let v = and(); while (tokens[i] === "||") { i++; const r = and(); v = v || r; } return v; };
  const and = () => { let v = not(); while (tokens[i] === "&&") { i++; const r = not(); v = v && r; } return v; };
  const not = () => (tokens[i] === "!" ? (i++, !not()) : atom());
  const atom = () => {
    const t = tokens[i++];
    if (t === "(") { const v = or(); if (tokens[i] === ")") i++; return v; }
    return t !== undefined && t !== ")" && t !== "&&" && t !== "||" && !!ctx[t];
  };
  if (!tokens.length) return true;
  const value = or();
  return i === tokens.length ? value : false;
}

// Given the strokes typed so far: the binding they complete (the last one wins), and whether a longer chord could still follow.
function matchChord(bindings, typed, ctx) {
  let exact = null, more = false;
  for (const b of bindings) {
    if (!evalWhen(b.when, ctx) || b.strokes.length < typed.length) continue;
    if (!typed.every((s, k) => b.strokes[k] === s)) continue;
    if (b.strokes.length === typed.length) exact = b; else more = true;
  }
  return { exact, more };
}

// ------------------------------------------------------------------ find in a file

// Where `query` is in `text`: [{ line (from 1), col (from 0), length }]. An empty match never counts. { error } when the pattern is not valid.
function findMatches(text, query, { caseSensitive = false, word = false, regex = false } = {}, limit = 5000) {
  if (!query) return { matches: [], error: "" };
  let source = regex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (word) source = `(?<![\\w])(?:${source})(?![\\w])`;
  let pattern;
  try { pattern = new RegExp(source, caseSensitive ? "g" : "gi"); } catch (err) { return { matches: [], error: String(err.message) }; }
  const matches = [];
  const lines = String(text).split("\n");
  for (let n = 0; n < lines.length && matches.length < limit; n++) {
    pattern.lastIndex = 0;
    let found;
    while ((found = pattern.exec(lines[n])) && matches.length < limit) {
      if (found[0].length === 0) { pattern.lastIndex++; continue; }
      matches.push({ line: n + 1, col: found.index, length: found[0].length });
    }
  }
  return { matches, error: "" };
}

// The column on screen of character `index` of a line, tabs counted to the next tab stop.
function visualColumn(line, index, tabSize = 4) {
  let col = 0;
  for (let i = 0; i < Math.min(index, line.length); i++) col += line[i] === "\t" ? tabSize - (col % tabSize) : 1;
  return col;
}

// The first match at or after (line, col), wrapping round; -1 when there are none. `backwards`: the one before instead.
function nextMatch(matches, line, col, backwards = false) {
  if (!matches.length) return -1;
  if (!backwards) {
    const at = matches.findIndex((m) => m.line > line || (m.line === line && m.col >= col));
    return at < 0 ? 0 : at;
  }
  for (let k = matches.length - 1; k >= 0; k--) if (matches[k].line < line || (matches[k].line === line && matches[k].col < col)) return k;
  return matches.length - 1;
}

// ------------------------------------------------------------------ outline of a file (the symbols the Outline view lists)

function outlineOf(text, language) {
  const lines = String(text).split("\n");
  const out = [];
  const add = (name, kind, line, depth = 0) => out.push({ name, kind, line: line + 1, depth });
  const lang = String(language || "").toLowerCase();
  if (lang === "markdown") {
    let fence = false;
    lines.forEach((l, i) => {
      if (/^\s*(```|~~~)/.test(l)) fence = !fence;
      const m = !fence && /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(l);
      if (m) add(m[2], "heading", i, m[1].length - 1);
    });
  } else if (["c", "cpp", "c++", "h", "objective-c"].includes(lang)) {
    let comment = false;
    lines.forEach((l, i) => {
      if (comment) { if (l.includes("*/")) comment = false; return; }
      if (/^\s*\/\*/.test(l) && !l.includes("*/")) { comment = true; return; }
      let m;
      if ((m = /^#\s*define\s+(\w+)/.exec(l))) add(m[1], "macro", i);
      else if ((m = /^(?:typedef\s+)?(struct|union|enum|class|namespace)\s+(\w+)/.exec(l)) && !/;\s*$/.test(l)) add(m[2], m[1], i);
      else if (/^[A-Za-z_][\w\s*&:<>,~]*[\s*&]([\w:~]+)\s*\([^;]*$/.test(l) || /^[A-Za-z_][\w\s*&:<>,~]*[\s*&]([\w:~]+)\s*\([^;{]*\)\s*(?:const\s*)?\{?\s*$/.test(l)) {
        const name = /([\w:~]+)\s*\(/.exec(l)[1];
        const next = lines.slice(i + 1, i + 6).find((x) => x.trim() !== "");
        // the Norm puts `{` alone on the next line; others put it at the end of the line, and a prototype ends with `;`
        if (!/^(if|while|for|switch|return|else|sizeof)$/.test(name) && (l.trimEnd().endsWith("{") || (next !== undefined && next.trim().startsWith("{")) || (!l.includes(")") && !/;/.test(l)))) add(name, "function", i);
      }
    });
  } else if (lang === "makefile") {
    lines.forEach((l, i) => {
      let m;
      if ((m = /^([A-Za-z_][\w.-]*)\s*[:+?]?=/.exec(l))) add(m[1], "variable", i);
      else if ((m = /^([\w.%/$()-]+(?:\s+[\w.%/$()-]+)*)\s*:(?!=)/.exec(l)) && !l.startsWith("\t")) add(m[1], "target", i);
    });
  } else if (["python", "py"].includes(lang)) {
    lines.forEach((l, i) => {
      const m = /^(\s*)(def|class)\s+(\w+)/.exec(l);
      if (m) add(m[3], m[2] === "def" ? "function" : "class", i, Math.floor(m[1].length / 4));
    });
  } else if (["shell", "bash", "sh", "zsh"].includes(lang)) {
    lines.forEach((l, i) => { const m = /^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\)\s*\{?/.exec(l) || /^\s*function\s+([A-Za-z_][\w-]*)/.exec(l); if (m) add(m[1], "function", i); });
  }
  return out;
}

// ------------------------------------------------------------------ diff of two texts (the Source Control view)

// Edit script from a to b (arrays of lines): [{ op: "eq" | "del" | "ins", a?: index, b?: index }]. Myers' algorithm with the common ends trimmed.
function diffLines(a, b, maxEdits = 3000) {
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length, endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) { endA--; endB--; }
  const ops = [];
  for (let i = 0; i < start; i++) ops.push({ op: "eq", a: i, b: i });
  const x = a.slice(start, endA), y = b.slice(start, endB);
  const middle = x.length || y.length ? myers(x, y, maxEdits) : [];
  for (const o of middle) ops.push(o.op === "eq" ? { op: "eq", a: o.a + start, b: o.b + start } : o.op === "del" ? { op: "del", a: o.a + start } : { op: "ins", b: o.b + start });
  for (let k = 0; k < a.length - endA; k++) ops.push({ op: "eq", a: endA + k, b: endB + k });
  return ops;
}

function myers(x, y, maxEdits) {
  const n = x.length, m = y.length, max = Math.min(n + m, maxEdits);
  const trace = [];
  let v = { 1: 0 };
  let found = -1;
  for (let d = 0; d <= max && found < 0; d++) {
    trace.push({ ...v });
    for (let k = -d; k <= d; k += 2) {
      let px = k === -d || (k !== d && v[k - 1] < v[k + 1]) ? v[k + 1] : v[k - 1] + 1;
      let py = px - k;
      while (px < n && py < m && x[px] === y[py]) { px++; py++; }
      v[k] = px;
      if (px >= n && py >= m) { found = d; break; }
    }
  }
  if (found < 0) {                                                                      // too different to be worth aligning: everything replaced
    return [...x.map((_, i) => ({ op: "del", a: i })), ...y.map((_, j) => ({ op: "ins", b: j }))];
  }
  const out = [];
  let px = n, py = m;
  for (let d = found; d > 0; d--) {
    const vd = trace[d];
    const k = px - py;
    const prevK = k === -d || (k !== d && vd[k - 1] < vd[k + 1]) ? k + 1 : k - 1;
    const prevX = vd[prevK], prevY = prevX - prevK;
    while (px > prevX && py > prevY) { px--; py--; out.push({ op: "eq", a: px, b: py }); }
    if (px === prevX) { py--; out.push({ op: "ins", b: py }); } else { px--; out.push({ op: "del", a: px }); }
  }
  while (px > 0 && py > 0) { px--; py--; out.push({ op: "eq", a: px, b: py }); }
  return out.reverse();
}

// Side by side rows: [{ left: { n, text } | null, right: { n, text } | null, kind: "eq" | "del" | "ins" | "chg" }]; a block of removed lines is
// paired with the added lines that follow it.
function diffRows(a, b) {
  const ops = diffLines(a, b);
  const rows = [];
  let i = 0;
  while (i < ops.length) {
    if (ops[i].op === "eq") { rows.push({ left: { n: ops[i].a + 1, text: a[ops[i].a] }, right: { n: ops[i].b + 1, text: b[ops[i].b] }, kind: "eq" }); i++; continue; }
    const dels = [], inss = [];
    while (i < ops.length && ops[i].op !== "eq") { (ops[i].op === "del" ? dels : inss).push(ops[i]); i++; }
    for (let k = 0; k < Math.max(dels.length, inss.length); k++) {
      const d = dels[k], s = inss[k];
      rows.push({ left: d ? { n: d.a + 1, text: a[d.a] } : null, right: s ? { n: s.b + 1, text: b[s.b] } : null, kind: d && s ? "chg" : d ? "del" : "ins" });
    }
  }
  return rows;
}

// Indexes of the first row of each block of changes.
function diffHunks(rows) {
  return rows.flatMap((r, i) => (r.kind !== "eq" && (i === 0 || rows[i - 1].kind === "eq") ? [i] : []));
}

// What a side by side diff shows: the changed rows with `context` rows around them. A longer run of rows that did not change is folded
// ("N hidden lines"); `open` has the first row of the folds the user opened. [{ kind: "rows" | "fold", from, to }], `to` not included.
function diffFold(rows, context = 3, open = []) {
  if (!rows.some((r) => r.kind !== "eq")) return rows.length ? [{ kind: "rows", from: 0, to: rows.length }] : [];
  const opened = new Set(open);
  const near = new Array(rows.length).fill(false);
  rows.forEach((r, i) => {
    if (r.kind !== "eq") for (let k = Math.max(0, i - context); k <= Math.min(rows.length - 1, i + context); k++) near[k] = true;
  });
  const out = [];
  for (let i = 0; i < rows.length;) {
    let j = i;
    while (j < rows.length && near[j] === near[i]) j++;
    const fold = !near[i] && j - i > 3 && !opened.has(i);                  // (hiding fewer rows than the line that says so would not help)
    const last = out[out.length - 1];
    if (!fold && last && last.kind === "rows") last.to = j;
    else out.push({ kind: fold ? "fold" : "rows", from: i, to: j });
    i = j;
  }
  return out;
}

// ------------------------------------------------------------------ the Source Control view

const SCM_KIND_TITLES = { modified: "Modified", added: "Added", deleted: "Deleted", renamed: "Renamed", untracked: "Untracked", conflict: "Conflict" };

// The groups of the view, from the files git reports ({ path, x, y, kind, from? }; x is the state in the index, y the state in the working
// tree). A file changed in both places is in both groups; a conflict is only in the first.
function scmGroups(files) {
  const groups = [
    { id: "merge", title: "Merge Changes", entries: [] },
    { id: "staged", title: "Staged Changes", entries: [] },
    { id: "changes", title: "Changes", entries: [] },
  ];
  for (const f of files) {
    if (f.kind === "conflict") { groups[0].entries.push({ ...f, letter: "!", staged: false }); continue; }
    if (f.x && f.x !== "?") groups[1].entries.push({ ...f, letter: f.x, staged: true });
    if ((f.y && f.y !== "?") || f.kind === "untracked") groups[2].entries.push({ ...f, letter: f.kind === "untracked" ? "U" : f.y, staged: false });
  }
  return groups.filter((g) => g.entries.length);
}

// For the explorer: path -> { letter, kind }, and the folders that hold a change (they get a dot).
function scmDecorations(files) {
  const byPath = {}, folders = new Set();
  for (const f of files) {
    byPath[f.path] = { letter: f.kind === "untracked" ? "U" : f.kind === "conflict" ? "!" : f.y || f.x, kind: f.kind };
    const parts = f.path.split("/");
    for (let i = 1; i < parts.length; i++) folders.add(parts.slice(0, i).join("/"));
  }
  return { byPath, folders: [...folders].sort() };
}

// ------------------------------------------------------------------ dropping a tab on an editor group

// Where in a box a pointer is, for dropping a tab: near an edge it splits the group on that side, in the middle it joins the group.
function dropZone(x, y, box, edge = 0.25) {
  const w = box.right - box.left, hgt = box.bottom - box.top;
  if (w <= 0 || hgt <= 0) return "center";
  const fx = (x - box.left) / w, fy = (y - box.top) / hgt;
  const left = fx, right = 1 - fx, top = fy, bottom = 1 - fy;
  const nearest = Math.min(left, right, top, bottom);
  if (nearest > edge) return "center";
  return nearest === left ? "left" : nearest === right ? "right" : nearest === top ? "up" : "down";
}

// The layouts of View > Editor Layout, as the grids they make from the tabs of all the groups.
function groupsPreset(state, preset) {
  const tabs = groupsAllTabs(state);
  const active = state.groups[state.active]?.active ?? tabs[0] ?? null;
  const shape = {
    single: { grid: { leaf: "g1" }, count: 1 },
    columns: { grid: { dir: "row", children: [{ leaf: "g1" }, { leaf: "g2" }], sizes: [1, 1] }, count: 2 },
    rows: { grid: { dir: "column", children: [{ leaf: "g1" }, { leaf: "g2" }], sizes: [1, 1] }, count: 2 },
    grid: { grid: { dir: "row", children: [{ dir: "column", children: [{ leaf: "g1" }, { leaf: "g3" }], sizes: [1, 1] }, { dir: "column", children: [{ leaf: "g2" }, { leaf: "g4" }], sizes: [1, 1] }], sizes: [1, 1] }, count: 4 },
  }[preset];
  if (!shape) return state;
  const next = { grid: clone(shape.grid), groups: {}, active: "g1", next: shape.count + 1 };
  for (let i = 1; i <= shape.count; i++) next.groups[`g${i}`] = { tabs: [], active: null, history: [] };
  // the tabs stay in the group they were in when that group still exists; the rest go to the first
  for (const key of tabs) {
    const was = groupsGroupOf(state, key);
    const where = next.groups[was] ? was : "g1";
    next.groups[where].tabs.push(key);
    next.groups[where].history.push(key);
  }
  for (const id of Object.keys(next.groups)) next.groups[id].active = state.groups[id]?.active && next.groups[id].tabs.includes(state.groups[id].active) ? state.groups[id].active : next.groups[id].tabs[0] ?? null;
  if (active && next.groups[groupsGroupOf(next, active)]) { next.active = groupsGroupOf(next, active); next.groups[next.active].active = active; }
  return next;
}

// ------------------------------------------------------------------ small things

// A file name as a shell word (a file dropped on a terminal is typed there): left alone when it needs no quoting, else in single quotes.
function shellQuote(path) {
  return /^[A-Za-z0-9_./+=:@%-]+$/.test(path) && !path.startsWith("-") ? path : `'${String(path).replace(/'/g, "'\\''")}'`;
}


const breadcrumbParts = (path) => String(path).split("/").filter(Boolean).map((name, i, all) => ({ name, path: all.slice(0, i + 1).join("/"), last: i === all.length - 1 }));

// The Ln/Col shown for a click or selection: the line (from 1) and column (from 1, tabs counted as one character, as VS Code does).
function lineColumn(text, offset) {
  const before = String(text).slice(0, Math.max(0, offset));
  const line = before.split("\n").length;
  return { line, col: before.length - (before.lastIndexOf("\n") + 1) + 1 };
}

// Order tabs: `from` goes before or after `to`.
function moveKey(keys, from, to, after = false) {
  if (from === to || !keys.includes(from) || !keys.includes(to)) return keys.slice();
  const rest = keys.filter((k) => k !== from);
  rest.splice(rest.indexOf(to) + (after ? 1 : 0), 0, from);
  return rest;
}

if (typeof module !== "undefined") {
  module.exports = {
    clone, gridIsLeaf, gridLeaves, gridSplit, gridRemove, gridNeighbor, gridSetSizes, gridEqualize,
    LOCATIONS, SIZE_LIMITS, layoutDefault, layoutReconcile, locationOf, containerOfView, layoutMoveContainer, layoutMoveView, layoutViewToNewContainer,
    layoutSetActive, layoutToggle, layoutSetPanelPosition, layoutResize, layoutReveal, layoutSetContainerHidden, layoutRevealView, layoutToggleCollapsed, layoutSet, layoutEffective,
    groupsNew, groupsGroupOf, groupsOpen, groupsCloseTab, groupsSplit, groupsCloseGroup, groupsActivateGroup, groupsMoveWithin, groupsFocusDirection, groupsAllTabs,
    termNew, termGroupOf, termPanes, termAdd, termSplit, termKill, termFocus, termRename, termFocusDirection, termActivePane, termAdopt,
    normalizeSettings, normalizeStroke, normalizeChord, strokeFromEvent, resolveBindings, evalWhen, matchChord,
    findMatches, visualColumn, nextMatch, outlineOf, diffLines, diffRows, diffHunks, diffFold, scmGroups, scmDecorations, SCM_KIND_TITLES, dropZone, groupsPreset, breadcrumbParts, lineColumn, moveKey, shellQuote,
  };
}
