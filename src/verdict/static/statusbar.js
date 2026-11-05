"use strict";

// The status bar: what is open and what is going on on the left, where you are in the file and the bell on the right. An item with a
// `command` runs it when clicked. Items draw themselves from the state when the page tells them it changed.

let chordHint = null;
let notificationCenter = null;

const STATUS_ITEMS = [
  { id: "project", side: "left", priority: 100, command: "workbench.action.files.openProject",
    text: () => (session?.repo ? (session.repo.name || session.repo.path || "project") : "no repository"), icon: () => "verdict", title: () => (session?.repo ? `${session.repo.url} — Open Project…` : "Open a project") },
  { id: "commit", side: "left", priority: 90, command: "workbench.view.scm", visible: () => !!session?.repo, icon: () => "branch",
    text: () => session.repo.commit, title: () => `${session.repo.commit} ${session.repo.subject} (${session.repo.author})` },
  { id: "problems", side: "left", priority: 80, command: "workbench.actions.view.problems", visible: () => !!session?.results?.length,
    text: () => { const c = statusCounts(); return `✖ ${c.fail}  ⚠ ${c.warn}`; }, title: () => "Problems: failed checks and warnings" },
  { id: "ssh", side: "left", priority: 60, visible: () => !!ssh, text: () => (ssh.ok ? `ssh: ${ssh.keys.length} key(s)` : "ssh: ⚠ not ready"), title: () => ssh.message },
  { id: "sandbox", side: "left", priority: 50, text: () => (sandboxUp ? "sandbox: ready" : "sandbox: unavailable (static checks only)"), title: () => "The container that builds and runs the code under review" },
  { id: "chord", side: "left", priority: 10, visible: () => !!chordHint, text: () => chordHint, title: () => "Waiting for the second key of the chord" },

  { id: "notifications", side: "right", priority: 10, command: "notifications.toggleList", icon: () => (notifications.doNotDisturb ? "bell-off" : "bell"),
    text: () => { const n = notifications.items.filter((i) => !i.read).length; return n ? String(n) : ""; }, title: () => "Notifications" },
  { id: "state", side: "right", priority: 20, text: () => stateLabel(), title: () => "What the review is doing" },
  { id: "language", side: "right", priority: 30, visible: () => !!tabs.get(activeTab)?.language, text: () => tabs.get(activeTab).language, title: () => "Language mode" },
  { id: "eol", side: "right", priority: 40, visible: () => !!tabs.get(activeTab)?.text, text: () => "LF", title: () => "End of line sequence" },
  { id: "encoding", side: "right", priority: 50, visible: () => !!tabs.get(activeTab)?.text, text: () => "UTF-8", title: () => "Select encoding" },
  { id: "indent", side: "right", priority: 60, visible: () => !!tabs.get(activeTab)?.text, command: "workbench.action.openSettings", text: () => `Tab Size: ${settings.get("editor.tabSize")}`, title: () => "Select indentation" },
  { id: "cursor", side: "right", priority: 70, visible: () => !!tabs.get(activeTab)?.text, command: "workbench.action.gotoLine",
    text: () => { const c = tabs.get(activeTab).cursor ?? { line: 1, col: 1, selected: 0 }; return `Ln ${c.line}, Col ${c.col}${c.selected ? ` (${c.selected} selected)` : ""}`; }, title: () => "Go to Line/Column" },
];

function statusCounts() {
  const c = { fail: 0, warn: 0 };
  for (const r of session?.results ?? []) { const k = shownStatus(r); if (k in c) c[k]++; }
  return c;
}

function stateLabel() {
  if (!session) return "";
  const label = session.ai.state === "running" ? `AI review: ${session.ai.step || "starting"}`
    : { idle: "ready", cloning: "cloning…", running: "running checks…", done: "done", error: "error" }[session.state];
  return session.message ? `${label}: ${session.message}` : label;
}

function buildStatusBar() {
  bus.on("notifications", () => refreshStatusBar());
  bus.on("chord", (typed) => { chordHint = typed ? `(${typed.map((s) => showKey(s, IS_MAC)).join(" ")}) was pressed. Waiting for second key of chord...` : null; refreshStatusBar(); });
  bus.on("cursor", () => refreshStatusBar());
  bus.on("tab:active", () => refreshStatusBar());
  refreshStatusBar();
}

function refreshStatusBar() {
  const bar = $("#statusbar");
  if (!bar) return;
  const entries = (which) => STATUS_ITEMS.filter((i) => i.side === which && (!i.visible || i.visible())).sort((a, b) => b.priority - a.priority)
    .map((item) => ({ item, text: item.text(), name: item.icon ? item.icon() : null, title: item.title?.() ?? "" }));
  const left = entries("left"), right = entries("right");
  bar.classList.toggle("busy", !!session && busy());
  // (drawn again only when something it shows changed: the page refreshes every second while a run goes on, and a click must not land on a button just rebuilt)
  const signature = JSON.stringify([left, right].map((list) => list.map((e) => [e.item.id, e.text, e.name, e.title, e.item.command ?? ""])));
  if (bar.dataset.sig === signature) return;
  bar.dataset.sig = signature;
  const make = ({ item, text, name, title }) => {
    const el = h(item.command ? "button" : "span", {
      class: `status-item status-${item.id}`, title, "data-status": item.id,
      onclick: item.command ? () => runCommand(item.command) : null,
    }, name ? icon(name, 14) : null, text ? h("span", { class: "status-text" }, text) : null);
    if (item.id === "notifications") el.classList.toggle("has-unread", notifications.items.some((i) => !i.read));
    return el;
  };
  bar.replaceChildren(h("div", { class: "status-left" }, left.map(make)), h("div", { class: "status-right" }, right.map(make)));
}

// The list behind the bell.
function toggleNotificationCenter() {
  if (notificationCenter) { closeNotificationCenter(); return; }
  for (const item of notifications.items) item.read = true;
  const list = h("div", { class: "notification-list" });
  const render = () => {
    list.replaceChildren(...(notifications.items.length ? [...notifications.items].reverse().map((item) => h("div", { class: `notification notification-${item.level}` },
      h("span", { class: "toast-icon" }, icon(item.level === "error" ? "error" : item.level === "warning" ? "warning" : "info", 16)),
      h("div", { class: "notification-body" }, h("div", { class: "notification-message" }, item.message),
        h("div", { class: "notification-meta" }, new Date(item.at).toTimeString().slice(0, 8), ...item.actions.map((a) => h("button", { class: "linklike", onclick: () => { closeNotificationCenter(); a.run(); } }, a.label)))))) : [h("div", { class: "notification-empty" }, "No new notifications")]));
  };
  render();
  notificationCenter = h("div", { id: "notification-center", role: "dialog", "aria-label": "Notifications" },
    h("div", { class: "notification-head" }, h("span", {}, "NOTIFICATIONS"),
      h("span", { class: "spacer" }),
      iconButton(notifications.doNotDisturb ? "bell-off" : "bell", notifications.doNotDisturb ? "Turn off Do Not Disturb" : "Do Not Disturb", () => { notifications.doNotDisturb = !notifications.doNotDisturb; closeNotificationCenter(); refreshStatusBar(); }),
      iconButton("trash", "Clear All Notifications", () => { clearNotifications(); render(); refreshStatusBar(); }),
      iconButton("x", "Hide Notification Center", closeNotificationCenter)),
    list);
  document.body.append(notificationCenter);
  refreshStatusBar();
  setTimeout(() => document.addEventListener("mousedown", outsideNotifications, true), 0);
}

function outsideNotifications(ev) {
  if (notificationCenter && !notificationCenter.contains(ev.target) && !ev.target.closest?.(".status-notifications")) closeNotificationCenter();
}

function closeNotificationCenter() {
  notificationCenter?.remove();
  notificationCenter = null;
  document.removeEventListener("mousedown", outsideNotifications, true);
}
