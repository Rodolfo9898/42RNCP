"use strict";

// Menus: the dropdowns of the menu bar and the context menus all come from here. An item is
//   "-"                                        a separator
//   { command: "id" }                           runs a command (its title, key and enabled state come from the command)
//   { label, run, key?, disabled?, checked?, submenu? }   anything else
// A `checked` can be a boolean or a function (so that a menu built once stays right).

let openMenus = [];        // the menus on screen, the first is the one the user opened
let menuCleanup = null;
let menuReturnFocus = null;

function closeMenus() {
  for (const m of openMenus) m.el.remove();
  openMenus = [];
  if (menuCleanup) { menuCleanup(); menuCleanup = null; }
  setContext("menuOpen", false);
  document.body.classList.remove("menu-open");
  bus.emit("menu", false);
  if (menuReturnFocus && document.contains(menuReturnFocus)) menuReturnFocus.focus?.();
  menuReturnFocus = null;
}

const resolveItem = (item) => {
  if (item === "-") return item;
  if (item.command) {
    const spec = commandRegistry.get(item.command);
    if (!spec) return { label: item.command, disabled: true };
    return {
      label: item.label ?? spec.menuTitle ?? spec.title, key: keyLabel(item.command), disabled: !commandEnabled(item.command) || item.disabled,
      checked: spec.checked ? spec.checked() : item.checked, run: () => runCommand(item.command, ...(item.args ?? [])),
    };
  }
  return { ...item, checked: typeof item.checked === "function" ? item.checked() : item.checked };
};

function menuElement(items, depth) {
  const resolved = items.map(resolveItem);
  const shown = resolved.filter((it, i) => !(it === "-" && (i === 0 || resolved[i - 1] === "-" || i === resolved.length - 1)));
  const el = h("div", { class: "menu", role: "menu", tabindex: "-1", "data-depth": String(depth) });
  const rows = shown.map((it) => {
    if (it === "-") return h("div", { class: "menu-sep", role: "separator" });
    const row = h("div", {
      class: `menu-item ${it.disabled ? "disabled" : ""} ${it.checked ? "checked" : ""} ${it.submenu ? "has-submenu" : ""}`, role: it.checked !== undefined ? "menuitemcheckbox" : "menuitem",
      "aria-disabled": it.disabled ? "true" : null, "aria-checked": it.checked !== undefined ? String(!!it.checked) : null, tabindex: "-1",
    },
    h("span", { class: "menu-check" }, it.checked ? icon("check", 14) : ""),
    h("span", { class: "menu-label" }, it.label),
    h("span", { class: "menu-key" }, it.submenu ? icon("chevron-right", 14) : it.key ?? ""));
    row.addEventListener("mouseenter", () => { focusRow(el, row); if (it.submenu && !it.disabled) openSubmenu(row, it.submenu, depth); else closeDeeper(depth); });
    row.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (it.disabled) return;
      if (it.submenu) { openSubmenu(row, it.submenu, depth, true); return; }
      closeMenus();
      it.run?.();
    });
    row._item = it;
    return row;
  });
  el.append(...rows);
  return el;
}

function focusRow(menu, row) {
  for (const r of $$(".menu-item.focus", menu)) r.classList.remove("focus");
  row.classList.add("focus");
}

function closeDeeper(depth) {
  while (openMenus.length > depth + 1) openMenus.pop().el.remove();
}

function openSubmenu(row, items, depth, focusFirst = false) {
  closeDeeper(depth);
  const box = row.getBoundingClientRect();
  const el = menuElement(items, depth + 1);
  placeMenu(el, box.right - 2, box.top - 4, depth + 1, box);
  if (focusFirst) { const first = $(".menu-item:not(.disabled)", el); if (first) focusRow(el, first); }
}

function placeMenu(el, x, y, depth, anchorBox = null) {
  $("#menu-layer").append(el);
  openMenus[depth] = { el };
  const box = el.getBoundingClientRect();
  const left = x + box.width > window.innerWidth - 4 ? Math.max(4, (anchorBox ? anchorBox.left - box.width + 2 : window.innerWidth - box.width - 4)) : x;
  const top = y + box.height > window.innerHeight - 4 ? Math.max(4, window.innerHeight - box.height - 4) : y;
  el.style.left = `${Math.max(0, left)}px`;
  el.style.top = `${Math.max(0, top)}px`;
}

function startMenu(items, place) {
  closeMenus();
  menuReturnFocus = document.activeElement;
  const el = menuElement(items, 0);
  place(el);
  setContext("menuOpen", true);
  document.body.classList.add("menu-open");
  const onKey = (ev) => menuKey(ev);
  const onOutside = (ev) => { if (!ev.target.closest?.(".menu") && !ev.target.closest?.("[data-menu-owner]")) closeMenus(); };
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("mousedown", onOutside, true);
  window.addEventListener("blur", closeMenus);
  window.addEventListener("resize", closeMenus);
  menuCleanup = () => {
    document.removeEventListener("keydown", onKey, true);
    document.removeEventListener("mousedown", onOutside, true);
    window.removeEventListener("blur", closeMenus);
    window.removeEventListener("resize", closeMenus);
  };
  bus.emit("menu", true);
  return el;
}

function showContextMenu(ev, items) {
  ev.preventDefault?.();
  startMenu(items, (el) => placeMenu(el, ev.clientX, ev.clientY, 0));
}

// Below the element (or above it, for the buttons at the bottom of the window).
function showMenuAt(anchor, items, direction = "down") {
  const box = anchor.getBoundingClientRect();
  startMenu(items, (el) => {
    $("#menu-layer").append(el);
    const mine = el.getBoundingClientRect();
    placeMenu(el, direction === "up" ? box.right : box.left, direction === "up" ? Math.max(4, box.bottom - mine.height) : box.bottom, 0);
    if (direction === "up") el.style.left = `${box.right}px`;
  });
}

function menuKey(ev) {
  const top = openMenus[openMenus.length - 1]?.el;
  if (!top) return;
  const rows = $$(".menu-item:not(.disabled)", top);
  const current = rows.findIndex((r) => r.classList.contains("focus"));
  const go = (i) => { ev.preventDefault(); ev.stopPropagation(); if (rows.length) focusRow(top, rows[(i + rows.length) % rows.length]); };
  if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); if (openMenus.length > 1) openMenus.pop().el.remove(); else closeMenus(); }
  else if (ev.key === "ArrowDown") go(current + 1);
  else if (ev.key === "ArrowUp") go(current < 0 ? -1 : current - 1);
  else if (ev.key === "Home") go(0);
  else if (ev.key === "End") go(rows.length - 1);
  else if (ev.key === "ArrowRight") {
    const row = rows[current];
    if (row && row._item.submenu) { ev.preventDefault(); ev.stopPropagation(); openSubmenu(row, row._item.submenu, openMenus.length - 1, true); }
    else bus.emit("menu:sideways", 1);
  } else if (ev.key === "ArrowLeft") {
    if (openMenus.length > 1) { ev.preventDefault(); ev.stopPropagation(); openMenus.pop().el.remove(); }
    else bus.emit("menu:sideways", -1);
  } else if (ev.key === "Enter" || ev.key === " ") {
    if (current >= 0) { ev.preventDefault(); ev.stopPropagation(); rows[current].click(); }
  }
}

// ------------------------------------------------------------------ the menu bar

const MENUBAR = [
  ["File", () => [
    { command: "workbench.action.files.openProject" }, { command: "verdict.addSubjectsFromLibrary" }, { command: "verdict.uploadSubjects" }, "-",
    { command: "workbench.action.closeActiveEditor" }, { command: "workbench.action.closeOtherEditors" }, { command: "workbench.action.closeAllEditors" }, "-",
    { command: "verdict.downloadVerdict" }, "-",
    { label: "Preferences", submenu: [{ command: "workbench.action.openSettings" }, { command: "workbench.action.openGlobalKeybindings" }, { command: "workbench.action.selectTheme" }] }, "-",
    { command: "workbench.action.reloadWindow" },
  ]],
  ["Edit", () => [
    { command: "editor.action.clipboardCopyAction" }, "-",
    { command: "actions.find" }, { command: "actions.findNext" }, { command: "actions.findPrevious" }, "-",
    { command: "workbench.action.findInFiles" },
  ]],
  ["Selection", () => [{ command: "editor.action.selectAll" }]],
  ["View", () => [
    { command: "workbench.action.showCommands" }, { command: "workbench.action.openView" }, "-",
    { label: "Appearance", submenu: [
      { command: "workbench.action.toggleFullScreen" }, { command: "workbench.action.toggleZenMode" }, "-",
      { command: "workbench.action.toggleSidebarVisibility" }, { command: "workbench.action.toggleAuxiliaryBar" }, { command: "workbench.action.toggleActivityBarVisibility" },
      { command: "workbench.action.toggleStatusbarVisibility" }, { command: "workbench.action.togglePanel" }, "-",
      { command: "workbench.action.moveSideBarRight" }, { command: "workbench.action.moveSideBarLeft" }, "-",
      { label: "Panel Position", submenu: [{ command: "workbench.action.positionPanelLeft" }, { command: "workbench.action.positionPanelBottom" }, { command: "workbench.action.positionPanelRight" }] },
      { command: "workbench.action.toggleMaximizedPanel" }, "-",
      { command: "workbench.action.zoomIn" }, { command: "workbench.action.zoomOut" }, { command: "workbench.action.zoomReset" }] },
    { label: "Editor Layout", submenu: [
      { command: "workbench.action.splitEditorUp" }, { command: "workbench.action.splitEditorDown" }, { command: "workbench.action.splitEditorLeft" }, { command: "workbench.action.splitEditorRight" }, "-",
      { command: "workbench.action.editorLayoutSingle" }, { command: "workbench.action.editorLayoutTwoColumns" }, { command: "workbench.action.editorLayoutTwoRows" }, { command: "workbench.action.editorLayoutGrid" }] }, "-",
    { command: "workbench.view.explorer" }, { command: "workbench.view.search" }, { command: "workbench.view.scm" }, { command: "workbench.view.subjects" }, { command: "workbench.view.run" }, { command: "workbench.view.review" }, "-",
    { command: "workbench.actions.view.problems" }, { command: "workbench.action.output.toggleOutput" }, { command: "workbench.action.terminal.toggleTerminal" }, "-",
    { command: "editor.action.toggleMinimap" }, { command: "breadcrumbs.toggle" },
  ]],
  ["Go", () => [
    { command: "workbench.action.navigateBack" }, { command: "workbench.action.navigateForward" }, "-",
    { command: "workbench.action.quickOpen" }, { command: "workbench.action.gotoSymbol" }, { command: "workbench.action.gotoLine" }, "-",
    { command: "workbench.action.nextEditor" }, { command: "workbench.action.previousEditor" }, { command: "workbench.action.focusNextGroup" }, { command: "workbench.action.focusPreviousGroup" },
  ]],
  ["Run", () => [
    { command: "verdict.run" }, "-", { command: "verdict.openClaude" }, { command: "verdict.aiReview" }, { command: "verdict.fixPrompt" }, "-", { command: "verdict.environment" },
  ]],
  ["Terminal", () => [
    { command: "workbench.action.terminal.new" }, { command: "workbench.action.terminal.split" }, { command: "workbench.action.terminal.kill" }, "-",
    { command: "workbench.action.terminal.focusNext" }, { command: "workbench.action.terminal.focusPrevious" }, { command: "workbench.action.terminal.rename" }, "-",
    { command: "workbench.action.terminal.moveToEditor" }, { command: "workbench.action.terminal.moveToPanel" }, "-", { command: "verdict.openClaude" },
  ]],
  ["Help", () => [
    { command: "workbench.action.welcome" }, { command: "workbench.action.openGlobalKeybindings" }, { command: "workbench.action.showCommands" }, "-", { command: "verdict.about" },
  ]],
];

function manageMenu() {
  return [
    { command: "workbench.action.showCommands" }, "-",
    { command: "workbench.action.openSettings" }, { command: "workbench.action.openGlobalKeybindings" }, { command: "workbench.action.selectTheme" }, "-",
    { command: "verdict.environment" }, "-",
    { command: "workbench.action.zoomIn" }, { command: "workbench.action.zoomOut" }, { command: "workbench.action.zoomReset" },
  ];
}

function customizeLayoutMenu() {
  return [
    { command: "workbench.action.toggleSidebarVisibility" }, { command: "workbench.action.toggleAuxiliaryBar" }, { command: "workbench.action.togglePanel" },
    { command: "workbench.action.toggleActivityBarVisibility" }, { command: "workbench.action.toggleStatusbarVisibility" }, "-",
    { command: "workbench.action.moveSideBarRight" }, { command: "workbench.action.moveSideBarLeft" }, "-",
    { label: "Panel Position", submenu: [{ command: "workbench.action.positionPanelLeft" }, { command: "workbench.action.positionPanelBottom" }, { command: "workbench.action.positionPanelRight" }] },
    { command: "workbench.action.toggleMaximizedPanel" }, "-",
    { command: "workbench.action.toggleZenMode" }, { command: "workbench.action.toggleFullScreen" }, "-", { command: "workbench.action.resetViewLocations" },
  ];
}

let menuBarOpen = -1;

function buildTitleBar() {
  const bar = $("#menubar");
  bar.setAttribute("role", "menubar");
  bar.replaceChildren(...MENUBAR.map(([name], i) => {
    const button = h("button", {
      class: "menubar-item", role: "menuitem", "aria-haspopup": "true", "data-menu-owner": name, tabindex: i === 0 ? "0" : "-1",
      onclick: () => (menuBarOpen === i ? closeMenus() : openMenuBar(i)),
      onmouseenter: () => { if (menuBarOpen >= 0 && menuBarOpen !== i) openMenuBar(i); },
      onkeydown: (ev) => {
        if (ev.key === "ArrowRight") { ev.preventDefault(); $$(".menubar-item", bar)[(i + 1) % MENUBAR.length].focus(); }
        else if (ev.key === "ArrowLeft") { ev.preventDefault(); $$(".menubar-item", bar)[(i + MENUBAR.length - 1) % MENUBAR.length].focus(); }
        else if (ev.key === "ArrowDown" || ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openMenuBar(i); }
      },
    }, name);
    return button;
  }));
  bus.on("menu", (open) => { if (!open) { menuBarOpen = -1; $$(".menubar-item", bar).forEach((b) => b.classList.remove("open")); } });
  bus.on("menu:sideways", (step) => { if (menuBarOpen >= 0) openMenuBar((menuBarOpen + step + MENUBAR.length) % MENUBAR.length); });

  $("#command-center").replaceChildren(
    h("button", { class: "command-center-box", title: "Search files by name (Go to File)", onclick: () => runCommand("workbench.action.quickOpen") },
      icon("search", 14), h("span", { id: "command-center-text" }, "verdict")));
  $("#title-actions").replaceChildren(
    iconButton("layout-sidebar", "Toggle Primary Side Bar", () => runCommand("workbench.action.toggleSidebarVisibility"), { cls: "title-toggle" }),
    iconButton("layout-panel", "Toggle Panel", () => runCommand("workbench.action.togglePanel"), { cls: "title-toggle" }),
    iconButton("layout-sidebar-right", "Toggle Secondary Side Bar", () => runCommand("workbench.action.toggleAuxiliaryBar"), { cls: "title-toggle" }),
    iconButton("layout", "Customize Layout...", (ev) => showMenuAt(ev.currentTarget, customizeLayoutMenu()), { cls: "title-toggle" }));
  $("#brand").replaceChildren(icon("verdict", 18));
}

function openMenuBar(i) {
  const buttons = $$(".menubar-item", $("#menubar"));
  menuBarOpen = i;
  showMenuAt(buttons[i], MENUBAR[i][1]());
  menuBarOpen = i;                                  // (startMenu closes the previous one, which resets this)
  buttons.forEach((b, k) => b.classList.toggle("open", k === i));
  const first = $(".menu-item:not(.disabled)", openMenus[0].el);
  if (first && document.activeElement?.classList?.contains("menubar-item") === false) focusRow(openMenus[0].el, first);
}

function refreshTitle() {
  const project = session?.repo ? (session.repo.name || session.repo.path || "verdict") : "verdict";
  const text = $("#command-center-text");
  if (text) text.textContent = project;
  const open = tabs.get(activeTab);
  document.title = open && open.kind !== "overview" ? `${open.title} — ${project}` : project === "verdict" ? "verdict" : `${project} — verdict`;
  const side = $$(".title-toggle")[0];
  if (side) side.replaceChildren(icon(layout?.sidebarSide === "right" ? "layout-sidebar-right" : "layout-sidebar", 16));
  const panelButton = $$(".title-toggle")[1];
  if (panelButton) panelButton.replaceChildren(icon(layout ? { bottom: "layout-panel", left: "layout-panel-left", right: "layout-panel-right" }[layout.locations.panel.position] : "layout-panel", 16));
  const sec = $$(".title-toggle")[2];
  if (sec) sec.replaceChildren(icon(layout?.sidebarSide === "right" ? "layout-sidebar" : "layout-sidebar-right", 16));
}
