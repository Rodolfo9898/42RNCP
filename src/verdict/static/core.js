"use strict";

// The small things everything else stands on: finding elements, talking to the server, storing settings, icons, notifications, dialogs.
// Everything shown comes from untrusted input (PDFs, repositories): build DOM with textContent only, never innerHTML.
// Shared helpers (h, markdown, rainbow brackets) are in lib.js; the pure models (layout, groups, keys, find, diff) are in model.js.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ------------------------------------------------------------------ browser storage that never throws

const store = {
  get(key, fallback = null) {
    try { const raw = localStorage.getItem(key); return raw === null ? fallback : JSON.parse(raw); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable: it lasts until the page is reloaded */ }
  },
  remove(key) {
    try { localStorage.removeItem(key); } catch { /* nothing to do */ }
  },
};

// ------------------------------------------------------------------ events between the parts of the page

const bus = (() => {
  const listeners = new Map();
  return {
    on(name, fn) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(fn);
      return () => listeners.get(name)?.delete(fn);
    },
    emit(name, ...args) {
      for (const fn of [...(listeners.get(name) ?? [])]) {
        try { fn(...args); } catch (err) { console.error(`${name} listener:`, err); }
      }
    },
  };
})();

// ------------------------------------------------------------------ the server

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

async function guarded(fn) {
  try { return await fn(); } catch (err) { notify(err.message, { level: "error" }); }
}

// ------------------------------------------------------------------ icons (drawn here: nothing is fetched)

const circle = (cx, cy, r) => `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
const box = (x, y, w, hgt, r = 0) => r
  ? `M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${hgt - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(w - 2 * r)}a${r} ${r} 0 0 1 ${-r} ${-r}v${-(hgt - 2 * r)}a${r} ${r} 0 0 1 ${r} ${-r}z`
  : `M${x} ${y}h${w}v${hgt}h${-w}z`;

const ICONS = {
  files: [box(9, 9, 13, 13, 2), "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"],
  search: [circle(11, 11, 8), "M21 21l-4.35-4.35"],
  branch: ["M6 3v12", circle(18, 6, 3), circle(6, 18, 3), "M18 9a9 9 0 0 1-9 9"],
  play: ["M5 3l14 9-14 9z"],
  book: ["M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z", "M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"],
  chat: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
  tool: ["M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"],
  gear: [circle(12, 12, 3), "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"],
  terminal: ["M4 17l6-6-6-6", "M12 19h8"],
  x: ["M18 6L6 18M6 6l12 12"],
  plus: ["M12 5v14M5 12h14"],
  minus: ["M5 12h14"],
  "chevron-right": ["M9 18l6-6-6-6"],
  "chevron-down": ["M6 9l6 6 6-6"],
  "chevron-up": ["M18 15l-6-6-6 6"],
  "chevron-left": ["M15 18l-6-6 6-6"],
  refresh: ["M23 4v6h-6", "M1 20v-6h6", "M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"],
  "collapse-all": ["M17 11l-5-5-5 5M17 18l-5-5-5 5"],
  "split-right": [box(3, 3, 18, 18, 2), "M12 3v18"],
  "split-down": [box(3, 3, 18, 18, 2), "M3 12h18"],
  trash: ["M3 6h18", "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2", "M10 11v6M14 11v6"],
  more: [circle(12, 12, 1), circle(19, 12, 1), circle(5, 12, 1)],
  maximize: ["M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"],
  restore: ["M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"],
  "layout-panel": [box(3, 3, 18, 18, 2), "M3 15h18"],
  "layout-panel-left": [box(3, 3, 18, 18, 2), "M9 3v18"],
  "layout-panel-right": [box(3, 3, 18, 18, 2), "M15 3v18"],
  "layout-sidebar": [box(3, 3, 18, 18, 2), "M9 3v18"],
  "layout-sidebar-right": [box(3, 3, 18, 18, 2), "M15 3v18"],
  layout: [box(3, 3, 18, 18, 2), "M3 9h18M9 21V9"],
  bell: ["M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9", "M13.73 21a2 2 0 0 1-3.46 0"],
  "bell-off": ["M13.73 21a2 2 0 0 1-3.46 0", "M18.63 13A17.89 17.89 0 0 1 18 8", "M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14", "M18 8a6 6 0 0 0-9.33-5", "M1 1l22 22"],
  warning: ["M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z", "M12 9v4M12 17h.01"],
  error: [circle(12, 12, 10), "M15 9l-6 6M9 9l6 6"],
  info: [circle(12, 12, 10), "M12 16v-4M12 8h.01"],
  check: ["M20 6L9 17l-5-5"],
  "check-circle": ["M22 11.08V12a10 10 0 1 1-5.93-9.14", "M22 4L12 14.01l-3-3"],
  file: ["M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z", "M13 2v7h7"],
  folder: ["M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"],
  upload: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M17 8l-5-5-5 5M12 3v12"],
  list: ["M8 6h13M8 12h13M8 18h13", "M3 6h.01M3 12h.01M3 18h.01"],
  pin: ["M12 17v5", "M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1z"],
  edit: ["M12 20h9", "M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"],
  sliders: ["M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"],
  command: ["M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3 3 3 0 0 0-3-3H6a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 3 3 0 0 0-3-3z"],
  shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", "M9 12l2 2 4-4"],
  copy: [box(9, 9, 13, 13, 2), "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"],
  "arrow-up": ["M12 19V5M5 12l7-7 7 7"],
  "arrow-down": ["M12 5v14M19 12l-7 7-7-7"],
  "regex": ["M17 3v10", "M12.67 5.5l8.66 5", "M12.67 10.5l8.66-5", "M9 17a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v2a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2z"],
  eye: ["M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z", circle(12, 12, 3)],
  "git-diff": [circle(6, 6, 3), circle(18, 18, 3), "M13 6h3a2 2 0 0 1 2 2v7", "M11 18H8a2 2 0 0 1-2-2V9"],
  verdict: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", "M9 12l2 2 4-4"],
  window: [box(3, 4, 18, 16, 2), "M3 9h18"],
  zap: ["M13 2L3 14h9l-1 8 10-12h-9z"],
  home: ["M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z", "M9 22V12h6v10"],
  "text-size": ["M4 7V4h16v3M9 20h6M12 4v16"],
};

// An inline SVG (stroke icons, 24 x 24 drawing, any size). Unknown names give an empty box rather than an error.
function icon(name, size = 16) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", `icon icon-${name}`);
  for (const d of ICONS[name] ?? []) {
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

// ------------------------------------------------------------------ settings

// The names of the colour themes and the `data-theme` of the page each one is (style.css has the colours).
const THEME_IDS = { "Dark Modern": "modern", "Dark+": "dark", "Light+": "light", "Solarized Dark": "solarized", "High Contrast": "hc" };
const THEMES = Object.keys(THEME_IDS);

// The settings editor is made from this list. `group` is the heading it appears under.
const SETTINGS = [
  { id: "workbench.colorTheme", group: "Workbench", type: "enum", options: THEMES, default: "Dark Modern", description: "Specifies the color theme used in the workbench." },
  { id: "window.zoomLevel", group: "Workbench", type: "number", min: -3, max: 5, default: 0, description: "Adjust the zoom level of the whole window. Each increment above 0 (e.g. 1) or below (e.g. -1) represents zooming 20% larger or smaller." },
  { id: "workbench.editor.showTabs", group: "Workbench", type: "boolean", default: true, description: "Controls whether opened editors show as tabs or not." },
  { id: "editor.fontSize", group: "Editor", type: "number", min: 8, max: 32, default: 13, description: "Controls the font size in pixels." },
  { id: "editor.tabSize", group: "Editor", type: "number", min: 1, max: 8, default: 4, description: "The number of spaces a tab is equal to." },
  { id: "editor.lineNumbers", group: "Editor", type: "enum", options: ["on", "off"], default: "on", description: "Controls the display of line numbers." },
  { id: "editor.minimap.enabled", group: "Editor", type: "boolean", default: true, description: "Controls whether the minimap is shown." },
  { id: "breadcrumbs.enabled", group: "Editor", type: "boolean", default: true, description: "Enable/disable navigation breadcrumbs." },
  { id: "editor.bracketPairColorization.enabled", group: "Editor", type: "boolean", default: true, description: "Controls whether bracket pair colorization is enabled or not: the colour is the nesting depth." },
  { id: "terminal.integrated.fontSize", group: "Terminal", type: "number", min: 8, max: 32, default: 13, description: "Controls the font size in pixels of the terminal." },
  { id: "terminal.integrated.cursorStyle", group: "Terminal", type: "enum", options: ["block", "line", "underline"], default: "block", description: "Controls the style of terminal cursor." },
  { id: "terminal.integrated.cursorBlinking", group: "Terminal", type: "boolean", default: true, description: "Controls whether the terminal cursor blinks." },
  { id: "terminal.integrated.tabs.location", group: "Terminal", type: "enum", options: ["right", "left"], default: "right", description: "Controls the location of the terminal list (the tabs of the terminals) relative to the terminal." },
  { id: "terminal.integrated.scrollback", group: "Terminal", type: "number", min: 500, max: 50000, default: 5000, description: "Controls the maximum amount of lines the terminal keeps in its buffer." },
  { id: "terminal.integrated.copyOnSelection", group: "Terminal", type: "boolean", default: false, description: "Controls whether text selected in the terminal will be copied to the clipboard." },
];

const settings = (() => {
  let values = normalizeSettings(store.get("verdict.settings", {}), SETTINGS);
  return {
    get: (id) => values[id],
    all: () => ({ ...values }),
    set(id, value) {
      const item = SETTINGS.find((s) => s.id === id);
      if (!item) return;
      const next = normalizeSettings({ ...values, [id]: value }, SETTINGS);
      if (next[id] === values[id]) return;
      values = next;
      store.set("verdict.settings", values);
      bus.emit("setting", id, values[id]);
    },
    reset(id) {
      const item = SETTINGS.find((s) => s.id === id);
      if (item) this.set(id, item.default);
    },
  };
})();

// Window zoom (Zoom In/Out): the text of the whole page and of the editor and the terminal grows by a fifth of its size for each step.
const zoomFactor = () => Math.round((1 + settings.get("window.zoomLevel") * 0.2) * 100) / 100;

// ------------------------------------------------------------------ notifications (the toasts, and the list behind the bell)

const notifications = { items: [], doNotDisturb: false, nextId: 1 };

// level: "info" | "warning" | "error". actions: [{ label, run }]. A toast shows for a few seconds; the list keeps what was said.
function notify(message, { level = "info", actions = [], silent = false } = {}) {
  const item = { id: notifications.nextId++, message: String(message), level, actions, at: Date.now(), read: false };
  notifications.items.push(item);
  if (notifications.items.length > 100) notifications.items.shift();
  bus.emit("notifications", item);
  if (!silent && !notifications.doNotDisturb) showToast(item);
  return item;
}

// The older name, still used all over: a failure unless it says it went well.
function toast(message, ok = false) {
  return notify(message, { level: ok ? "info" : "error" });
}

function showToast(item) {
  const host = $("#toasts");
  if (!host) return;
  const el = h("div", { class: `toast toast-${item.level}`, role: "alert" },
    h("span", { class: "toast-icon" }, icon(item.level === "error" ? "error" : item.level === "warning" ? "warning" : "info", 16)),
    h("span", { class: "toast-message" }, item.message),
    h("span", { class: "toast-actions" }, item.actions.map((a) => h("button", { class: "linklike", onclick: () => { el.remove(); a.run(); } }, a.label))),
    h("button", { class: "icon-button toast-close", title: "Close", onclick: () => el.remove() }, icon("x", 14)));
  host.append(el);
  while (host.children.length > 4) host.firstChild.remove();
  setTimeout(() => el.remove(), item.level === "error" ? 10000 : 6000);
}

function clearNotifications() {
  notifications.items.length = 0;
  bus.emit("notifications", null);
}

// ------------------------------------------------------------------ dialogs

function dialog(title, body, buttons) {
  const d = $("#dialog");
  d.replaceChildren(h("h3", {}, title), body, h("div", { class: "buttons" }, buttons));
  $("#modal").hidden = false;
  bus.emit("dialog", true);
}
const closeDialog = () => { if (!$("#modal").hidden) { $("#modal").hidden = true; bus.emit("dialog", false); } };
const dialogOpen = () => !$("#modal").hidden;

if (typeof module !== "undefined") module.exports = { ICONS };

// ------------------------------------------------------------------ the clipboard

// (navigator.clipboard only exists on https and on localhost: reached by another address, the page cannot copy)
const copyText = (text, what) => Promise.resolve().then(() => navigator.clipboard.writeText(text)).then(() => notify(`Copied ${what}.`), () => notify("Could not copy: the browser does not allow it on this address.", { level: "error" }));
