"use strict";

// Every command of the page. The menus, the command palette, the status bar and the keyboard all run these (the machinery is in commands.js).
// The ids and the keys are VS Code's. The browser keeps a few keys for itself and no page can take them (Cmd/Ctrl+W, T and N, Ctrl+Tab,
// Ctrl+PageUp/PageDown): those commands have another key here. Every key can be changed in the Keyboard Shortcuts editor.

const mac = (onMac, elsewhere) => (IS_MAC ? onMac : elsewhere);
// A key that is the Control key on every platform (a page sees Ctrl on Windows and Linux as "mod", and "ctrl" only on a Mac, where "mod" is Cmd).
const ctl = (rest) => (IS_MAC ? `ctrl+${rest}` : `mod+${rest}`);
const defineCommands = (specs) => specs.forEach(registerCommand);
const needProject = () => "Open a project first (File > Open Project).";
const hasProject = () => !!session?.repo;
const panelOf = () => layout.locations.panel;
const sideOf = (where) => layout.locations[where];

// A view of the panel (the terminal, the output) opens, or hides the part it is in when it is already on show.
function toggleViewPart(viewId, afterOpen = null) {
  const container = containerOfView(layout, viewId);
  const where = container && locationOf(layout, container);
  if (!where) return;
  const loc = layout.locations[where];
  if (loc.visible && loc.active === container && !layout.zen) { setLayout(layoutToggle(layout, where, false)); return; }
  setLayout(layoutRevealView(layout, viewId));
  afterOpen?.();
}

function showView(viewId, afterOpen = null) {
  setLayout(layoutRevealView(layout, viewId));
  afterOpen?.();
}

function focusIn(selector) {
  requestAnimationFrame(() => {
    const target = $(selector);
    const field = target && (target.matches("input, textarea, select, [tabindex]") ? target : $("input, textarea, select, button, [tabindex]", target));
    field?.focus();
  });
}

function stepEditorGroup(step) { cycleGroup(step); const key = editors.groups[editors.active]?.active; if (key) showTab(key); }

const zoomBy = (delta) => settings.set("window.zoomLevel", delta === 0 ? 0 : settings.get("window.zoomLevel") + delta);

// ------------------------------------------------------------------ the workbench: parts, layout, zoom

defineCommands([
  { id: "workbench.action.showCommands", title: "Show All Commands", category: "View", keys: ["mod+shift+p", "f1"], inTerminal: true, run: () => openQuickInput(">") },
  { id: "workbench.action.quickOpen", title: "Go to File...", category: "File", keys: "mod+p", inTerminal: true, run: () => openQuickInput("") },
  { id: "workbench.action.gotoLine", title: "Go to Line/Column...", keys: ctl("g"), when: "!terminalFocus", run: () => openQuickInput(":") },
  { id: "workbench.action.gotoSymbol", title: "Go to Symbol in Editor...", keys: "mod+shift+o", run: () => openQuickInput("@") },
  { id: "workbench.action.openView", title: "Open View...", category: "View", run: () => openViewPicker() },

  { id: "workbench.action.toggleSidebarVisibility", title: "Toggle Primary Side Bar Visibility", menuTitle: "Primary Side Bar", category: "View", keys: "mod+b", inTerminal: true,
    checked: () => sideOf("sidebar").visible, run: () => setLayout(layoutToggle(layout, "sidebar")) },
  { id: "workbench.action.toggleAuxiliaryBar", title: "Toggle Secondary Side Bar Visibility", menuTitle: "Secondary Side Bar", category: "View", keys: "mod+alt+b", inTerminal: true,
    checked: () => sideOf("secondary").visible, run: () => setLayout(layoutToggle(layout, "secondary")) },
  { id: "workbench.action.togglePanel", title: "Toggle Panel Visibility", menuTitle: "Panel", category: "View", keys: "mod+j", inTerminal: true,
    checked: () => panelOf().visible, run: () => setLayout(layoutToggle(layout, "panel")) },
  { id: "workbench.action.toggleActivityBarVisibility", title: "Toggle Activity Bar Visibility", menuTitle: "Activity Bar", category: "View",
    checked: () => layout.activityBar, run: () => setLayout(layoutSet(layout, "activityBar", !layout.activityBar)) },
  { id: "workbench.action.toggleStatusbarVisibility", title: "Toggle Status Bar Visibility", menuTitle: "Status Bar", category: "View",
    checked: () => layout.statusBar, run: () => setLayout(layoutSet(layout, "statusBar", !layout.statusBar)) },
  { id: "workbench.action.toggleMaximizedPanel", title: "Toggle Maximized Panel", category: "View",
    checked: () => panelOf().maximized, run: () => setLayout(layoutSet(layoutToggleVisible(layout, "panel"), "maximized", !panelOf().maximized)) },
  { id: "workbench.action.positionPanelLeft", title: "Move Panel Left", menuTitle: "Left", category: "View", checked: () => panelOf().position === "left", run: () => setLayout(layoutSetPanelPosition(layout, "left")) },
  { id: "workbench.action.positionPanelBottom", title: "Move Panel To Bottom", menuTitle: "Bottom", category: "View", checked: () => panelOf().position === "bottom", run: () => setLayout(layoutSetPanelPosition(layout, "bottom")) },
  { id: "workbench.action.positionPanelRight", title: "Move Panel Right", menuTitle: "Right", category: "View", checked: () => panelOf().position === "right", run: () => setLayout(layoutSetPanelPosition(layout, "right")) },
  { id: "workbench.action.moveSideBarRight", title: "Move Primary Side Bar Right", category: "View", enabled: () => layout.sidebarSide !== "right", run: () => setLayout(layoutSet(layout, "sidebarSide", "right")) },
  { id: "workbench.action.moveSideBarLeft", title: "Move Primary Side Bar Left", category: "View", enabled: () => layout.sidebarSide !== "left", run: () => setLayout(layoutSet(layout, "sidebarSide", "left")) },
  { id: "workbench.action.toggleSidebarPosition", title: "Toggle Primary Side Bar Position", category: "View", run: () => setLayout(layoutSet(layout, "sidebarSide", layout.sidebarSide === "left" ? "right" : "left")) },
  { id: "workbench.action.toggleZenMode", title: "Toggle Zen Mode", menuTitle: "Zen Mode", category: "View", keys: "mod+k z", checked: () => layout.zen, run: () => setLayout(layoutSet(layout, "zen", !layout.zen)) },
  { id: "workbench.action.exitZenMode", title: "Exit Zen Mode", category: "View", keys: "escape escape", when: "zenMode && !inputFocus", hidden: true, run: () => setLayout(layoutSet(layout, "zen", false)) },
  { id: "workbench.action.toggleFullScreen", title: "Toggle Full Screen", menuTitle: "Full Screen", category: "View", keys: mac("ctrl+mod+f", "f11"), inTerminal: true,
    checked: () => !!document.fullscreenElement, run: () => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.()) },
  { id: "workbench.action.zoomIn", title: "Zoom In", category: "View", run: () => zoomBy(1) },
  { id: "workbench.action.zoomOut", title: "Zoom Out", category: "View", run: () => zoomBy(-1) },
  { id: "workbench.action.zoomReset", title: "Reset Zoom", category: "View", run: () => zoomBy(0) },
  { id: "workbench.action.resetViewLocations", title: "Reset View Locations", category: "View", run: () => { store.remove(LAYOUT_KEY); setLayout(layoutReconcile(null, modelRegistry())); notify("The views are back where they started."); } },
  { id: "workbench.action.focusSideBar", title: "Focus into Primary Side Bar", category: "View", keys: "mod+0", run: () => { setLayout(layoutToggle(layout, "sidebar", true)); focusIn("#sidebar"); } },
  { id: "workbench.action.focusPanel", title: "Focus into Panel", category: "View", run: () => { setLayout(layoutToggle(layout, "panel", true)); focusIn("#panel"); } },
  { id: "workbench.action.focusActiveEditorGroup", title: "Focus Active Editor Group", category: "View", run: () => tabs.get(activeTab)?.view.focus({ preventScroll: true }) },
  { id: "workbench.action.reloadWindow", title: "Reload Window", category: "Developer", run: () => location.reload() },
  { id: "workbench.action.welcome", title: "Welcome", category: "Help", run: () => showTab("overview") },
  { id: "workbench.action.openSettings", title: "Open Settings", category: "Preferences", keys: "mod+,", inTerminal: true, run: () => openSettings() },
  { id: "workbench.action.openGlobalKeybindings", title: "Open Keyboard Shortcuts", category: "Preferences", keys: "mod+k mod+s", run: () => openKeybindings() },
  { id: "workbench.action.selectTheme", title: "Color Theme", menuTitle: "Color Theme", category: "Preferences", keys: "mod+k mod+t", run: () => pickTheme() },
  { id: "workbench.action.files.openProject", title: "Open Project...", category: "File", keys: "mod+o", enabled: () => !busy(), unavailable: () => "Wait for what is running to finish.", run: () => guarded(openClone) },
  { id: "notifications.toggleList", title: "Toggle Notifications", category: "Notifications", run: () => toggleNotificationCenter() },
  { id: "notifications.clearAll", title: "Clear All Notifications", category: "Notifications", run: () => { clearNotifications(); refreshStatusBar(); } },
  { id: "notifications.toggleDoNotDisturbMode", title: "Toggle Do Not Disturb Mode", category: "Notifications", checked: () => notifications.doNotDisturb, run: () => { notifications.doNotDisturb = !notifications.doNotDisturb; refreshStatusBar(); } },
]);

function layoutToggleVisible(current, where) {
  return current.locations[where].visible ? current : layoutToggle(current, where, true);
}

async function openViewPicker() {
  const names = { sidebar: "Side Bar", secondary: "Secondary Side Bar", panel: "Panel" };
  const items = [];
  for (const where of ["sidebar", "panel", "secondary"]) {
    for (const cid of layout.locations[where].order) {
      for (const vid of viewsOf(cid)) items.push({ label: viewTitle(viewSpecs.get(vid)), detail: containerTitle(cid), section: names[where], viewId: vid });
    }
  }
  const chosen = await quickPick({ title: "Open View", placeholder: "Select a view to open", items });
  if (chosen) showView(chosen.viewId);
}

// ------------------------------------------------------------------ views

defineCommands([
  { id: "workbench.view.explorer", title: "Show Explorer", menuTitle: "Explorer", category: "View", keys: "mod+shift+e", run: () => { showView("files"); focusIn("#tree"); } },
  { id: "workbench.view.search", title: "Show Search", menuTitle: "Search", category: "View", run: () => findInFiles() },
  { id: "workbench.action.findInFiles", title: "Find in Files", category: "Search", keys: "mod+shift+f", run: () => findInFiles() },
  { id: "workbench.view.scm", title: "Show Source Control", menuTitle: "Source Control", category: "View", keys: ctl("shift+g"), run: () => { showView("scm"); loadScm({ force: true }); } },
  { id: "workbench.view.subjects", title: "Show Subjects", menuTitle: "Subjects", category: "View", run: () => showView("subjects") },
  { id: "workbench.view.run", title: "Show Run", menuTitle: "Run", category: "View", keys: "mod+shift+d", run: () => showView("run") },
  { id: "workbench.view.review", title: "Show Review", menuTitle: "Review", category: "View", run: () => showView("review") },
  { id: "workbench.actions.view.problems", title: "Show Problems", menuTitle: "Problems", category: "View", keys: "mod+shift+m", run: () => showView("checklist") },
  { id: "workbench.action.output.toggleOutput", title: "Toggle Output", menuTitle: "Output", category: "View", keys: "mod+shift+u", run: () => toggleViewPart("log") },
  { id: "workbench.view.improvements", title: "Show Improvements", menuTitle: "Improvements", category: "View", run: () => showView("improvementsList") },
  { id: "workbench.view.rules", title: "Show Subject Rules", menuTitle: "Subject Rules", category: "View", run: () => showView("rulesList") },
  { id: "workbench.view.outline", title: "Show Outline", category: "View", run: () => showView("outline") },
  { id: "workbench.files.action.refreshFilesExplorer", title: "Refresh Explorer", category: "File", run: () => guarded(loadTree) },
  { id: "workbench.files.action.collapseExplorerFolders", title: "Collapse Folders in Explorer", category: "File", run: () => collapseAll() },
  { id: "workbench.files.revealActiveFileInExplorer", title: "Reveal Active File in Explorer", category: "File", enabled: () => !!tabs.get(activeTab)?.path, run: (key) => revealInExplorer(tabs.get(typeof key === "string" ? key : activeTab).path) },
  { id: "workbench.files.revealInExplorer", title: "Reveal in Explorer", category: "File", hidden: true, run: (path) => { if (typeof path === "string") revealInExplorer(path); } },
  { id: "search.action.clearSearchResults", title: "Clear Search Results", category: "Search", run: () => { searchState.results = null; searchState.query = ""; const v = viewSpecs.get("search"); if (v.input) v.input.value = ""; renderSearch(); } },
  { id: "search.action.refreshSearchResults", title: "Refresh Search Results", category: "Search", enabled: () => !!searchState.query, run: () => runSearch() },
  { id: "git.refresh", title: "Refresh", category: "Git", run: () => loadScm({ force: true }) },
  { id: "git.openChange", title: "Open Changes", category: "Git", enabled: () => !!changeOf(tabs.get(activeTab)?.path), run: () => { const f = changeOf(tabs.get(activeTab).path); return guarded(() => openDiff(f.path, { staged: !f.y && !!f.x, old: f.from })); } },
]);

// ------------------------------------------------------------------ editors: tabs, groups, layout, find

const nextChange = (step) => () => tabs.get(activeTab)?.diff?.step(step);

defineCommands([
  { id: "workbench.action.showEditorsInActiveGroup", title: "Show Opened Editors", category: "View", enabled: () => tabs.size > 0, run: (group) => pickOpenEditor(typeof group === "string" ? group : editors.active) },
  { id: "workbench.action.showAllEditors", title: "Show All Opened Editors", category: "View", keys: "mod+k mod+p", enabled: () => tabs.size > 0, run: () => pickOpenEditor(null) },
  { id: "workbench.action.closeActiveEditor", title: "Close Editor", category: "View", keys: "alt+w", when: "!findInputFocus && !searchFocus", enabled: () => !!tabs.get(activeTab)?.closable, run: () => closeTab(activeTab) },
  { id: "workbench.action.closeOtherEditors", title: "Close Other Editors in Group", category: "View", enabled: () => !!tabs.get(activeTab), run: () => closeTabs("others", activeTab) },
  { id: "workbench.action.closeEditorsToTheRight", title: "Close Editors to the Right in Group", category: "View", enabled: () => !!tabs.get(activeTab), run: () => closeTabs("right", activeTab) },
  { id: "workbench.action.closeAllEditors", title: "Close All Editors", category: "View", keys: "mod+k mod+w", enabled: () => tabs.size > 0, run: () => closeTabs("all", activeTab) },
  { id: "workbench.action.closeEditorsInGroup", title: "Close All Editors in Group", category: "View", keys: "mod+k w", run: () => { for (const key of [...(editors.groups[editors.active]?.tabs ?? [])]) if (tabs.get(key)?.closable && !isSession(key)) closeTab(key); } },
  { id: "workbench.action.closeGroup", title: "Close Editor Group", category: "View", enabled: () => gridLeaves(editors.grid).length > 1, run: () => closeGroup(editors.active) },
  { id: "workbench.action.keepEditor", title: "Keep Open", category: "View", keys: "mod+k enter", enabled: () => !!tabs.get(activeTab)?.preview, run: () => pinTab(activeTab) },
  { id: "workbench.action.nextEditor", title: "Open Next Editor", category: "View", keys: "alt+pagedown", run: () => cycleTab(1) },
  { id: "workbench.action.previousEditor", title: "Open Previous Editor", category: "View", keys: "alt+pageup", run: () => cycleTab(-1) },
  { id: "workbench.action.navigateBack", title: "Go Back", category: "Go", keys: mac("ctrl+-", "alt+left"), when: "!inputFocus && !terminalFocus", run: () => navigate(-1) },
  { id: "workbench.action.navigateForward", title: "Go Forward", category: "Go", keys: mac("ctrl+shift+-", "alt+right"), when: "!inputFocus && !terminalFocus", run: () => navigate(1) },

  { id: "workbench.action.splitEditor", title: "Split Editor", menuTitle: "Split Right", category: "View", keys: "mod+\\", when: "!terminalFocus", run: () => splitEditor(editors.active, "right") },
  { id: "workbench.action.splitEditorRight", title: "Split Editor Right", menuTitle: "Split Right", category: "View", run: () => splitEditor(editors.active, "right") },
  { id: "workbench.action.splitEditorLeft", title: "Split Editor Left", menuTitle: "Split Left", category: "View", run: () => splitEditor(editors.active, "left") },
  { id: "workbench.action.splitEditorDown", title: "Split Editor Down", menuTitle: "Split Down", category: "View", run: () => splitEditor(editors.active, "down") },
  { id: "workbench.action.splitEditorUp", title: "Split Editor Up", menuTitle: "Split Up", category: "View", run: () => splitEditor(editors.active, "up") },
  { id: "workbench.action.splitEditorOrthogonal", title: "Split Editor Orthogonal", category: "View", keys: "mod+k mod+\\", run: () => splitEditor(editors.active, "down") },
  { id: "workbench.action.editorLayoutSingle", title: "Single Column Editor Layout", menuTitle: "Single", category: "View", run: () => resetEditorLayout("single") },
  { id: "workbench.action.editorLayoutTwoColumns", title: "Two Columns Editor Layout", menuTitle: "Two Columns", category: "View", run: () => resetEditorLayout("columns") },
  { id: "workbench.action.editorLayoutTwoRows", title: "Two Rows Editor Layout", menuTitle: "Two Rows", category: "View", run: () => resetEditorLayout("rows") },
  { id: "workbench.action.editorLayoutGrid", title: "Grid Editor Layout (2x2)", menuTitle: "Grid (2x2)", category: "View", run: () => resetEditorLayout("grid") },
  { id: "workbench.action.focusFirstEditorGroup", title: "Focus First Editor Group", category: "View", keys: "mod+1", run: () => focusGroupAt(0) },
  { id: "workbench.action.focusSecondEditorGroup", title: "Focus Second Editor Group", category: "View", keys: "mod+2", run: () => focusGroupAt(1) },
  { id: "workbench.action.focusThirdEditorGroup", title: "Focus Third Editor Group", category: "View", keys: "mod+3", run: () => focusGroupAt(2) },
  { id: "workbench.action.focusNextGroup", title: "Focus Next Editor Group", category: "View", keys: "mod+k mod+right", run: () => stepEditorGroup(1) },
  { id: "workbench.action.focusPreviousGroup", title: "Focus Previous Editor Group", category: "View", keys: "mod+k mod+left", run: () => stepEditorGroup(-1) },
  { id: "workbench.action.focusLeftGroup", title: "Focus Left Editor Group", category: "View", keys: "mod+k left", run: () => focusGroup("left") },
  { id: "workbench.action.focusRightGroup", title: "Focus Right Editor Group", category: "View", keys: "mod+k right", run: () => focusGroup("right") },
  { id: "workbench.action.focusAboveGroup", title: "Focus Editor Group Above", category: "View", keys: "mod+k up", run: () => focusGroup("up") },
  { id: "workbench.action.focusBelowGroup", title: "Focus Editor Group Below", category: "View", keys: "mod+k down", run: () => focusGroup("down") },
  { id: "workbench.action.moveEditorToNextGroup", title: "Move Editor into Next Group", category: "View", enabled: () => gridLeaves(editors.grid).length > 1 && !!tabs.get(activeTab), run: () => moveActiveEditor(1) },
  { id: "workbench.action.moveEditorToPreviousGroup", title: "Move Editor into Previous Group", category: "View", enabled: () => gridLeaves(editors.grid).length > 1 && !!tabs.get(activeTab), run: () => moveActiveEditor(-1) },

  { id: "editor.action.toggleMinimap", title: "Toggle Minimap", menuTitle: "Minimap", category: "View", checked: () => settings.get("editor.minimap.enabled"), run: () => settings.set("editor.minimap.enabled", !settings.get("editor.minimap.enabled")) },
  { id: "breadcrumbs.toggle", title: "Toggle Breadcrumbs", menuTitle: "Breadcrumbs", category: "View", checked: () => settings.get("breadcrumbs.enabled"), run: () => settings.set("breadcrumbs.enabled", !settings.get("breadcrumbs.enabled")) },
  { id: "workbench.action.toggleTabsVisibility", title: "Toggle Tab Visibility", category: "View", checked: () => settings.get("workbench.editor.showTabs"), run: () => settings.set("workbench.editor.showTabs", !settings.get("workbench.editor.showTabs")) },
  { id: "editor.action.toggleRainbowBrackets", title: "Toggle Bracket Pair Colorization", category: "View", checked: () => settings.get("editor.bracketPairColorization.enabled"), run: () => settings.set("editor.bracketPairColorization.enabled", !settings.get("editor.bracketPairColorization.enabled")) },

  { id: "actions.find", title: "Find", category: "Edit", keys: "mod+f", when: "fileEditor && !terminalFocus", run: () => openFind() },
  { id: "actions.findNext", title: "Find Next", category: "Edit", keys: mac(["mod+g", "f3"], "f3"), when: "fileEditor", run: () => (find.widget && !find.widget.hidden ? stepFind(1) : openFind()) },
  { id: "actions.findPrevious", title: "Find Previous", category: "Edit", keys: mac(["mod+shift+g", "shift+f3"], "shift+f3"), when: "fileEditor", run: () => (find.widget && !find.widget.hidden ? stepFind(-1) : openFind()) },
  { id: "editor.action.selectAll", title: "Select All", category: "Edit", keys: "mod+a", when: "fileEditor && editorFocus && !inputFocus", run: () => selectAllInEditor() },
  { id: "editor.action.clipboardCopyAction", title: "Copy", category: "Edit", run: () => { if (!document.execCommand("copy")) notify("Select some text first.", { level: "info" }); } },

  { id: "workbench.action.compareEditor.nextChange", title: "Go to Next Change", category: "Compare", keys: ["alt+f5", "f7"], when: "diffEditor", run: nextChange(1) },
  { id: "workbench.action.compareEditor.previousChange", title: "Go to Previous Change", category: "Compare", keys: ["shift+alt+f5", "shift+f7"], when: "diffEditor", run: nextChange(-1) },
  { id: "toggle.diff.renderSideBySide", title: "Toggle Inline View", category: "Compare", enabled: () => tabs.get(activeTab)?.kind === "diff", run: () => { const d = tabs.get(activeTab).diff; d.setInline(!d.inline); renderEditors(); } },
]);

// A list of what is open (the group asked for, or every group), the most recently used first.
async function pickOpenEditor(groupId) {
  const keys = (groupId ? editors.groups[groupId]?.tabs ?? [] : groupsAllTabs(editors)).filter((k) => tabs.has(k));
  const recent = [...tabHistory].reverse();
  const order = [...keys].sort((a, b) => (recent.indexOf(a) + 1 || 1e6) - (recent.indexOf(b) + 1 || 1e6));
  const items = order.map((key) => ({ label: tabs.get(key).title, detail: tabs.get(key).path && tabs.get(key).path.includes("/") ? tabs.get(key).path.slice(0, tabs.get(key).path.lastIndexOf("/")) : "", key, picked: key === activeTab }));
  const chosen = await quickPick({ title: "Opened Editors", placeholder: "Select an editor to open", items });
  if (chosen) showTab(chosen.key);
}

function focusGroupAt(index) {
  const id = gridLeaves(editors.grid)[index];
  if (!id) return;
  activateGroup(id);
  const key = editors.groups[id].active;
  if (key) showTab(key);
}

function moveActiveEditor(step) {
  const ids = gridLeaves(editors.grid);
  const to = ids[(ids.indexOf(editors.active) + step + ids.length) % ids.length];
  moveTabToGroup(activeTab, to);
  showTab(activeTab);
}

function selectAllInEditor() {
  const tab = tabs.get(activeTab);
  if (!tab?.srcEl || !tab.text) return;
  selectOffsets(tab.srcEl, 0, tab.text.length);
  reportCursor(tab);
}

// ------------------------------------------------------------------ terminals

const inShellPane = () => !!termActivePane(terminals);

defineCommands([
  { id: "workbench.action.terminal.toggleTerminal", title: "Toggle Terminal", menuTitle: "Terminal", category: "View", keys: ctl("`"), inTerminal: true,
    run: () => toggleViewPart("terminals", () => { if (hasProject() && !termPanes(terminals).length) newTerminal(); else { const pane = termActivePane(terminals); if (pane) focusPane(pane); } }) },
  { id: "workbench.action.terminal.new", title: "Create New Terminal", menuTitle: "New Terminal", category: "Terminal", keys: ctl("shift+`"), inTerminal: true,
    enabled: hasProject, unavailable: needProject, run: () => newTerminal() },
  { id: "workbench.action.terminal.split", title: "Split Terminal", category: "Terminal", keys: mac("mod+\\", "mod+shift+5"), when: "terminalFocus", inTerminal: true,
    enabled: inShellPane, unavailable: () => "Open a terminal first.", run: () => splitTerminal("right") },
  { id: "workbench.action.terminal.splitDown", title: "Split Terminal Down", category: "Terminal", enabled: inShellPane, run: () => splitTerminal("down") },
  { id: "workbench.action.terminal.kill", title: "Kill the Active Terminal Instance", menuTitle: "Kill Terminal", category: "Terminal", enabled: inShellPane, run: () => killTerminal() },
  { id: "workbench.action.terminal.focusNext", title: "Focus Next Terminal Group", category: "Terminal", enabled: inShellPane, run: () => cycleTerminal(1) },
  { id: "workbench.action.terminal.focusPrevious", title: "Focus Previous Terminal Group", category: "Terminal", enabled: inShellPane, run: () => cycleTerminal(-1) },
  { id: "workbench.action.terminal.focusNextPane", title: "Focus Next Terminal in Group", category: "Terminal", keys: mac("ctrl+alt+right", "alt+right"), when: "terminalFocus", inTerminal: true, enabled: inShellPane, run: () => cyclePane(1) },
  { id: "workbench.action.terminal.focusPreviousPane", title: "Focus Previous Terminal in Group", category: "Terminal", keys: mac("ctrl+alt+left", "alt+left"), when: "terminalFocus", inTerminal: true, enabled: inShellPane, run: () => cyclePane(-1) },
  { id: "workbench.action.terminal.focusPaneUp", title: "Focus Terminal Above", category: "Terminal", keys: mac("ctrl+alt+up", "alt+up"), when: "terminalFocus", inTerminal: true, enabled: inShellPane, run: () => focusPaneDirection("up") },
  { id: "workbench.action.terminal.focusPaneDown", title: "Focus Terminal Below", category: "Terminal", keys: mac("ctrl+alt+down", "alt+down"), when: "terminalFocus", inTerminal: true, enabled: inShellPane, run: () => focusPaneDirection("down") },
  { id: "workbench.action.terminal.rename", title: "Rename the Currently Active Terminal", menuTitle: "Rename Terminal", category: "Terminal", enabled: inShellPane, run: () => { showTerminalView(); renameTerminal(termActivePane(terminals)); } },
  { id: "workbench.action.terminal.moveToEditor", title: "Move Terminal into Editor Area", category: "Terminal", enabled: inShellPane, run: () => moveTerminalToEditor() },
  { id: "workbench.action.terminal.moveToPanel", title: "Move Terminal into Panel", category: "Terminal", enabled: () => !!tabs.get(activeTab)?.moveToPanel, run: () => tabs.get(activeTab).moveToPanel() },
  { id: "workbench.action.terminal.clear", title: "Clear", category: "Terminal", enabled: inShellPane, run: () => terminalSessions.get(termActivePane(terminals))?.term?.clear() },
]);

// ------------------------------------------------------------------ the review: what the buttons of the old top bar were

defineCommands([
  { id: "verdict.run", title: "Run Checks", category: "Verdict", keys: "mod+shift+b", enabled: () => hasProject() && session.subjects.length > 0 && !busy(),
    unavailable: () => (!hasProject() ? needProject() : !session.subjects.length ? "Add at least one subject PDF first." : "Wait for what is running to finish."), run: () => guarded(run) },
  { id: "verdict.openClaude", title: "Open Claude", category: "Verdict", enabled: hasProject, unavailable: needProject, run: () => guarded(() => openTerminal()) },
  { id: "verdict.aiReview", title: "AI Review", category: "Verdict", enabled: () => hasProject() && !busy() && session.results.length > 0 && llm.configured,
    unavailable: () => (!llm.configured ? "Not configured: set ANTHROPIC_API_KEY, or LLM_BASE_URL + LLM_API_KEY + LLM_MODEL, in .env (see the README)." : !session.results.length ? "Run the checks first." : "Wait for what is running to finish."), run: () => guarded(startAi) },
  { id: "verdict.fixPrompt", title: "Write a Fix Prompt", category: "Verdict", enabled: () => hasProject() && !busy() && session.results.length > 0, unavailable: () => "Run the checks first.", run: () => guarded(openFixPrompt) },
  { id: "verdict.environment", title: "Check the Environment", category: "Verdict", run: () => guarded(openEnvironment) },
  { id: "verdict.addSubjectsFromLibrary", title: "Add Subjects from the Library...", category: "Verdict", run: () => guarded(openLibrary) },
  { id: "verdict.uploadSubjects", title: "Upload Subject PDFs...", category: "Verdict", run: () => guarded(() => openUpload()) },
  { id: "verdict.showVerdict", title: "Show the Verdict", category: "Verdict", run: () => showTab("overview") },
  { id: "verdict.downloadVerdict", title: "Download verdict.md", category: "Verdict", enabled: () => !!session?.results?.length, unavailable: () => "Run the checks first.", run: () => { window.location.href = `/api/sessions/${sid}/verdict.md?download=true`; } },
  { id: "verdict.about", title: "About", category: "Help", run: () => showAbout() },
]);
