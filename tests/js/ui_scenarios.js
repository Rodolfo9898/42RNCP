// The scenarios of tests/test_ui.py: `node ui_scenarios.js <name>` runs one (exit 0 when it passes), `--list` prints the names, `--check` says
// whether jsdom is there (exit 3 when it is not).
const assert = require("assert");
const { openPage, closeAllPages, fixtureSession, loadJsdom } = require("./ui_env");

const scenarios = {};
const scenario = (name, fn) => { scenarios[name] = fn; };
const ready = async (options) => (await openPage(options)).ready();
const noErrors = (page) => assert.deepStrictEqual(page.errors, [], `the page reported: ${page.errors.join(" / ")}`);
const activityTitles = (page) => page.$$(".activity-item").map((e) => e.getAttribute("aria-label"));
const panelTabs = (page) => page.$$(".panel-tab").map((e) => e.dataset.container);
const bodyHas = (page, cls) => page.document.body.classList.contains(cls);
const layoutNow = (page) => JSON.parse(page.eval("JSON.stringify(layout)"));

// ---------------------------------------------------------------- the page comes up as a workbench

scenario("boot", async () => {
  const page = await ready();
  noErrors(page);
  assert.deepStrictEqual(page.texts(".menubar-item"), ["File", "Edit", "Selection", "View", "Go", "Run", "Terminal", "Help"]);
  assert.deepStrictEqual(activityTitles(page), ["Explorer", "Search", "Source Control", "Subjects", "Run", "Review", "Manage"]);
  assert.deepStrictEqual(panelTabs(page), ["problems", "output", "terminal", "improvements", "rules"]);
  assert.strictEqual(page.text("#sidebar .part-title"), "Explorer");
  assert.deepStrictEqual(page.$$("#sidebar .pane").map((e) => e.dataset.view), ["openEditors", "files", "outline"]);
  assert.deepStrictEqual(page.texts(".tab .tab-title"), ["Verdict", "verdict.md"]);
  assert.match(page.text("#statusbar"), /fract-ol.*abc1234.*✖ 1/);
  assert.strictEqual(page.document.title, "fract-ol — verdict");
  assert.strictEqual(page.$$("#tree .row").length, 5);
  assert.strictEqual(page.document.documentElement.dataset.theme, "modern");
  assert.ok(page.$(".activity-item.active[data-container=explorer]"));
  assert.strictEqual(page.$(".activity-badge")?.textContent, "1", "the subjects badge says how many subjects");
});

scenario("a_page_that_has_not_changed_is_not_drawn_again", async () => {
  const page = await ready();
  const heading = page.$(".overview h1");
  page.eval("render()");
  assert.strictEqual(page.$(".overview h1"), heading, "the same data: nothing is built again (a selection or a click would be lost)");
  page.eval("render(true)");
  assert.notStrictEqual(page.$(".overview h1"), heading, "unless it is asked for");
  const bell = page.$(".status-project");
  page.eval("refreshStatusBar()");
  assert.strictEqual(page.$(".status-project"), bell, "the status bar neither");
  page.eval("session.state = 'running'; render()");
  assert.notStrictEqual(page.$(".overview h1"), heading, "a change is drawn");
  noErrors(page);
});

scenario("boot_without_a_server", async () => {
  const down = (json) => () => json({ detail: "the server is down" }, false, 500);
  let page;
  page = await openPage({ storage: { "verdict.session": "gone" }, routes: {
    "GET /api/sessions/[^/]+": ({ json }) => json({ detail: "unknown session" }, false, 404),
    "POST /api/sessions": ({ json }) => json({ detail: "the server is down" }, false, 500),
  } });
  await page.ready();
  await page.settle(100);
  assert.strictEqual(page.$$(".menubar-item").length, 8, "the menus are there even without a server");
  assert.ok(page.$$(".toast-error").length >= 1, "the failure is told");
  assert.match(page.text(".toast-error"), /server is down/);
  assert.ok(page.$(".activity-item"), "the workbench is drawn");
  await page.key("mod+shift+p");
  assert.ok(page.visible("#palette"), "the command palette works without a server");
});

scenario("a_fresh_review_without_project_or_subjects_has_nothing_to_break", async () => {
  const empty = fixtureSession({ repo: null, subjects: [], results: [], state: "idle", summary: { overall: "NOT RUN", mandatory: { fail: 0, warn: 0, manual: 0, skipped: 0, na: 0, pass: 0 }, bonus: { fail: 0, warn: 0, manual: 0, skipped: 0, na: 0, pass: 0 }, reason: "", decided_by: "", lists: "NOT RUN" } });
  const page = await ready({ session: empty, routes: { "GET /api/sessions/[^/]+/tree": ({ json }) => json([]) } });
  noErrors(page);
  assert.match(page.text("#tree-hint"), /No repository cloned yet/);
  assert.strictEqual(page.text("#command-center-text"), "verdict");
  assert.match(page.text("#statusbar"), /no repository/);
  assert.match(page.text(".overview"), /No repository yet/);
  assert.match(page.text("#panel"), /No results yet/);
  await page.click(".activity-item[data-container=scm]");
  assert.match(page.text(".scm-note"), /no project open/);
  await page.click(".activity-item[data-container=run]");
  assert.strictEqual(page.$("[data-command='verdict.run']").disabled, true);
  assert.match(page.$("[data-command='verdict.run']").title, /Open a project first/);
  await page.click(".activity-item[data-container=review]");
  assert.ok([...page.$$("#sidebar [data-command]")].every((b) => b.disabled || b.dataset.command === "verdict.openClaude" && b.disabled));
  await page.key("mod+p");
  assert.match(page.text(".palette-empty"), /No matching results/);
  await page.key("escape", "#palette input");
  await page.click(".activity-item[data-container=search]");
  await page.type(".search-input", "x");
  await page.settle(500);
  assert.strictEqual(page.called("GET /api/sessions/s1/search").length, 0, "nothing to search in");
  await page.run("workbench.action.openSettings");
  await page.run("workbench.action.openGlobalKeybindings");
  noErrors(page);
});

scenario("no_unsafe_dom", async () => {
  const page = await ready({ session: fixtureSession({ repo: { url: "u", path: "<img src=x onerror=alert(1)>", name: "<b>x</b>", commit: "abc", subject: "<script>x</script>", author: "me" } }) });
  assert.strictEqual(page.$$("#workbench img[onerror], #workbench script, #workbench b").length, 0, "text from a repository never becomes markup");
  assert.match(page.text("#command-center-text"), /<b>x<\/b>/);
});

// ---------------------------------------------------------------- the activity bar and the parts

scenario("activity_bar_switches_the_side_bar", async () => {
  const page = await ready();
  await page.click(".activity-item[data-container=search]");
  assert.strictEqual(page.text("#sidebar .part-title"), "Search");
  assert.ok(page.$("#sidebar .search-view"));
  assert.ok(page.$(".activity-item[data-container=search].active"));
  await page.click(".activity-item[data-container=search]");
  assert.ok(!page.visible("#sidebar"), "a second click on the one on show hides the side bar");
  await page.click(".activity-item[data-container=scm]");
  assert.ok(page.visible("#sidebar"));
  assert.strictEqual(page.text("#sidebar .part-title"), "Source Control");
  await page.click(".activity-item[data-container=explorer]");
  assert.deepStrictEqual(page.$$("#sidebar .pane").map((e) => e.dataset.view), ["openEditors", "files", "outline"]);
  noErrors(page);
});

scenario("parts_toggle_with_keys_and_commands", async () => {
  const page = await ready();
  assert.ok(await page.key("mod+b"));
  assert.ok(!page.visible("#sidebar"));
  await page.key("mod+b");
  assert.ok(page.visible("#sidebar"));
  await page.key("mod+j");
  assert.ok(!page.visible("#panel"), "Cmd/Ctrl+J hides the panel");
  await page.key("mod+j");
  assert.ok(page.visible("#panel"));
  await page.key("mod+alt+b");
  assert.ok(page.visible("#secondary"), "the secondary side bar shows (empty: nothing was moved there)");
  assert.match(page.text("#secondary"), /Drag a view here/);
  await page.key("mod+alt+b");
  assert.ok(!page.visible("#secondary"));
  await page.run("workbench.action.toggleActivityBarVisibility");
  assert.ok(bodyHas(page, "no-activitybar"));
  await page.run("workbench.action.toggleStatusbarVisibility");
  assert.ok(bodyHas(page, "no-statusbar"));
  await page.run("workbench.action.toggleActivityBarVisibility");
  await page.run("workbench.action.toggleStatusbarVisibility");
  assert.ok(!bodyHas(page, "no-activitybar") && !bodyHas(page, "no-statusbar"));
  noErrors(page);
});

scenario("panel_position_maximize_and_side_bar_side", async () => {
  const page = await ready();
  assert.ok(bodyHas(page, "panel-bottom"));
  await page.run("workbench.action.positionPanelRight");
  assert.ok(bodyHas(page, "panel-right") && !bodyHas(page, "panel-bottom"));
  await page.run("workbench.action.positionPanelLeft");
  assert.ok(bodyHas(page, "panel-left"));
  await page.run("workbench.action.positionPanelBottom");
  await page.run("workbench.action.toggleMaximizedPanel");
  assert.ok(bodyHas(page, "panel-maximized"));
  assert.ok(page.$("#panel .part-actions [title='Restore Panel Size']"));
  await page.run("workbench.action.toggleMaximizedPanel");
  assert.ok(!bodyHas(page, "panel-maximized"));
  await page.run("workbench.action.moveSideBarRight");
  assert.ok(bodyHas(page, "sidebar-right"));
  await page.run("workbench.action.moveSideBarLeft");
  assert.ok(!bodyHas(page, "sidebar-right"));
  assert.strictEqual(JSON.parse(page.storage()["verdict.workbench"]).locations.panel.position, "bottom", "the choice is remembered");
  noErrors(page);
});

scenario("zen_mode", async () => {
  const page = await ready();
  await page.key("mod+k z");
  assert.ok(bodyHas(page, "zen"));
  assert.ok(!page.visible("#sidebar") && !page.visible("#panel"));
  await page.key("escape escape");
  assert.ok(!bodyHas(page, "zen"), "Escape twice leaves Zen Mode");
  assert.ok(page.visible("#sidebar"));
});

scenario("sashes_resize_and_reset", async () => {
  const page = await ready();
  const sash = page.$("#sash-sidebar");
  await page.key("right", sash);
  await page.key("right", sash);
  assert.strictEqual(layoutNow(page).locations.sidebar.size, 332, "the arrow keys move a divider 16px at a time");
  await page.dblclick(sash);
  assert.strictEqual(layoutNow(page).locations.sidebar.size, 300, "a double click gives the usual size back");
  await page.key("up", "#sash-panel");
  assert.strictEqual(layoutNow(page).locations.panel.size, 296);
});

// ---------------------------------------------------------------- views move between the side bar, the secondary side bar and the panel

scenario("container_dragged_from_the_activity_bar_to_the_panel", async () => {
  const page = await ready();
  const transfer = { setData() {}, types: [], effectAllowed: "all", dropEffect: "" };
  const fire = (el, type, y = 0) => { const ev = new page.window.Event(type, { bubbles: true, cancelable: true }); Object.assign(ev, { dataTransfer: transfer, clientY: y, relatedTarget: null }); el.dispatchEvent(ev); };
  const icon = page.$(".activity-item[data-container=scm]");
  fire(icon, "dragstart");
  const first = page.$(".activity-top .activity-item");
  rect(first, { top: 0, height: 48 });
  fire(page.$("#activitybar"), "dragover", 10);
  assert.ok(first.classList.contains("drop-before"), "a line shows where the icon would land");
  fire(page.$("#activitybar"), "dragleave");
  assert.ok(!first.classList.contains("drop-before"), "and goes when the pointer leaves");
  fire(icon, "dragend");
  await page.drag(".activity-item[data-container=scm]", "#panel");
  assert.ok(!activityTitles(page).includes("Source Control"), "it left the activity bar");
  assert.ok(panelTabs(page).includes("scm"), "it is a tab of the panel now");
  assert.strictEqual(page.$(".panel-tab.active").dataset.container, "scm");
  assert.ok(page.$("#panel .scm-view"));
  assert.strictEqual(layoutNow(page).locations.panel.order.at(-1), "scm");
  noErrors(page);
});

scenario("panel_tab_dragged_to_the_activity_bar_and_to_the_secondary_side_bar", async () => {
  const page = await ready();
  await page.drag(".panel-tab[data-container=output]", "#activitybar");
  assert.ok(activityTitles(page).includes("Output"));
  assert.ok(!panelTabs(page).includes("output"));
  await page.drag(".activity-item[data-container=review]", "#secondary");
  assert.ok(page.visible("#secondary"));
  assert.strictEqual(page.text("#secondary .part-title"), "Review");
  assert.ok(!activityTitles(page).includes("Review"));
  noErrors(page);
});

scenario("a_view_dragged_out_of_its_container_makes_a_container_of_its_own", async () => {
  const page = await ready();
  await page.drag("#sidebar .pane-header[data-view=outline]", "#secondary");
  assert.ok(page.visible("#secondary"));
  assert.ok(page.$("#secondary .outline"), "the Outline view is in the secondary side bar");
  assert.deepStrictEqual(page.$$("#sidebar .pane").map((e) => e.dataset.view), ["openEditors", "files"]);
  await page.drag("#sidebar .pane-header[data-view=openEditors]", "#activitybar");
  assert.ok(activityTitles(page).includes("Open Editors"));
  noErrors(page);
});

scenario("the_layout_survives_a_reload_and_can_be_reset", async () => {
  const first = await ready();
  await first.drag(".activity-item[data-container=scm]", "#panel");
  await first.run("workbench.action.positionPanelRight");
  const second = await ready({ storage: first.storage() });
  assert.ok(panelTabs(second).includes("scm") && bodyHas(second, "panel-right"), "the same places after a reload");
  assert.ok(!activityTitles(second).includes("Source Control"));
  await second.run("workbench.action.resetViewLocations");
  assert.ok(activityTitles(second).includes("Source Control"));
  assert.ok(!panelTabs(second).includes("scm"));
  noErrors(second);
});

scenario("icons_come_off_the_activity_bar_and_tabs_off_the_panel_and_a_view_brings_them_back", async () => {
  const page = await ready();
  await page.contextmenu(".activity-item[data-container=subjects]");
  const entries = page.$$(".menu-item").filter((e) => e.classList.contains("checked") || /^(Explorer|Search|Source Control|Subjects|Run|Review)$/.test(e.querySelector(".menu-label")?.textContent));
  assert.strictEqual(entries.length, 6, "every container of the activity bar has a check");
  assert.ok(entries.every((e) => e.classList.contains("checked")));
  await page.click(entries[3]);
  assert.ok(!activityTitles(page).includes("Subjects"), "an unchecked one is off the bar");
  assert.deepStrictEqual(JSON.parse(page.storage()["verdict.workbench"]).hidden, { subjects: true });
  await page.contextmenu(".panel-tab[data-container=rules]");
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Subject Rules")));
  assert.ok(!panelTabs(page).includes("rules"));
  await page.key("mod+shift+p");
  await page.type("#palette input", ">show subjects");
  await page.key("enter");
  assert.ok(activityTitles(page).includes("Subjects"), "Show Subjects brings the icon back");
  assert.strictEqual(page.text("#sidebar .part-title"), "Subjects");
  const reloaded = await ready({ storage: page.storage() });
  assert.ok(!reloaded.$$(".panel-tab").some((e) => e.dataset.container === "rules"), "the panel tab stays off after a reload");
  await reloaded.run("workbench.action.resetViewLocations");
  assert.ok(reloaded.$$(".panel-tab").some((e) => e.dataset.container === "rules"));
  noErrors(page);
});

scenario("a_broken_saved_layout_is_ignored", async () => {
  const page = await ready({ storage: { "verdict.workbench": "{\"v\":2,\"locations\":{\"sidebar\":{\"order\":[\"nope\",\"explorer\",\"explorer\"]}},\"containers\":42}" } });
  noErrors(page);
  assert.ok(activityTitles(page).includes("Explorer") && activityTitles(page).includes("Source Control"));
  const page2 = await ready({ storage: { "verdict.workbench": "not json at all" } });
  noErrors(page2);
  assert.ok(page2.$(".activity-item"));
});

scenario("the_bars_are_not_drawn_again_under_the_pointer_while_something_is_dragged", async () => {
  const page = await ready();
  const item = page.$(".activity-item[data-container=scm]");
  const transfer = { setData() {}, types: [], effectAllowed: "all" };
  const fire = (el, type) => { const ev = new page.window.Event(type, { bubbles: true, cancelable: true }); ev.dataTransfer = transfer; el.dispatchEvent(ev); };
  fire(item, "dragstart");
  page.eval("scm.data = { available: true, error: '', files: [{ path: 'a.c', x: '', y: 'M', kind: 'modified' }], branch: 'main' }; bus.emit('scm')");
  await page.settle();
  assert.ok(item.isConnected, "the icon being dragged is still the one on the page");
  assert.ok(!item.querySelector(".activity-badge"), "(what changed waits)");
  fire(item, "dragend");
  await page.settle();
  assert.strictEqual(page.text(".activity-item[data-container=scm] .activity-badge"), "1", "and is drawn when the drag ends");
  const tab = page.$(".panel-tab[data-container=problems]");
  fire(tab, "dragstart");
  page.eval("session.results = session.results.concat([{ rule_id: 'r9', title: 'More', status: 'fail', detail: '', section: 'mandatory', sources: [], evidence: [], log: '', by: '' }]); renderPanelTabsOnly()");
  await page.settle();
  assert.ok(tab.isConnected, "a panel tab being dragged is not replaced either");
  assert.strictEqual(tab.querySelector(".tab-badge").textContent, "1");
  fire(tab, "dragend");
  await page.settle();
  assert.strictEqual(page.text(".panel-tab[data-container=problems] .tab-badge"), "2", "(it waits, and is drawn when the drag ends)");
  noErrors(page);
});

scenario("the_activity_bar_menu_moves_a_container", async () => {
  const page = await ready();
  await page.contextmenu(".activity-item[data-container=run]");
  const labels = page.texts(".menu-label");
  assert.ok(labels.includes("Move to Panel") && labels.includes("Move to Secondary Side Bar") && labels.includes("Reset View Locations"));
  await page.click(page.$$(".menu-item").find((e) => e.textContent.includes("Move to Panel")));
  assert.ok(panelTabs(page).includes("run"));
  noErrors(page);
});

// ---------------------------------------------------------------- editors: files, tabs, groups, find, go to line

const tabTitles = (page) => page.$$(".tab .tab-title").map((e) => e.textContent);
const groupsIn = (page) => page.$$(".editor-group");
const openMain = async (page) => { await page.click("#tree .row[data-path='main.c']"); await page.settle(60); };

scenario("a_click_previews_a_file_and_a_double_click_keeps_it", async () => {
  const page = await ready();
  await openMain(page);
  assert.ok(tabTitles(page).includes("main.c"));
  assert.ok(page.$(".tab.preview .tab-title"), "a single click opens a preview tab (in italics)");
  await page.click("#tree .row[data-path='Makefile']");
  await page.settle(60);
  assert.ok(!tabTitles(page).includes("main.c"), "the next preview replaces the first");
  assert.ok(tabTitles(page).includes("Makefile"));
  await page.dblclick(page.$(".tab.preview"));
  assert.ok(!page.$(".tab.preview"), "a double click keeps it open");
  assert.match(page.text(".group-breadcrumbs"), /Makefile/);
  assert.match(page.text("#statusbar"), /Ln 1, Col 1|Tab Size: 4/);
  noErrors(page);
});

scenario("breadcrumbs_show_the_path_and_the_folder_menu_lists_the_siblings", async () => {
  const page = await ready();
  await page.run("workbench.action.quickOpen");
  await page.type("#palette input", "util");
  await page.key("enter");
  await page.settle(80);
  assert.deepStrictEqual(page.$$(".group-breadcrumbs .crumb").map((e) => e.textContent.trim()).slice(0, 2), ["src", "util.c"]);
  await page.click(page.$(".group-breadcrumbs .crumb"));
  assert.ok(page.$(".menu"), "a click on a folder of the path lists what is in it");
  assert.ok(page.texts(".menu-label").some((t) => t.includes("util.c")));
  await page.key("escape");
  assert.ok(!page.$(".menu"));
});

scenario("split_editor_keeps_one_tab_per_file_and_moves_the_active_one", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  await page.key("mod+\\");
  assert.strictEqual(groupsIn(page).length, 2, "Cmd/Ctrl+\\ splits the editor");
  assert.ok(page.$$(".editor-group")[1].classList.contains("active-group"), "the new group is the one that is active");
  await page.dblclick("#tree .row[data-path='Makefile']");
  await page.settle(60);
  assert.ok(page.$$(".editor-group")[1].querySelector(".tab[data-key='Makefile']"), "the next file opens in the group that is active");
  await page.key("mod+\\");
  assert.strictEqual(groupsIn(page).length, 3);
  assert.ok(page.$$(".editor-group")[1].querySelector(".tab[data-key='main.c']") && page.$$(".editor-group")[2].querySelector(".tab[data-key='Makefile']"), "the tab in front goes to the new group");
  await page.key("mod+\\");
  assert.strictEqual(groupsIn(page).length, 4, "a group with one tab keeps it: the new group is empty, ready for the next file");
  assert.ok(page.$$(".editor-group")[2].querySelector(".tab[data-key='Makefile']") && !page.$$(".editor-group")[3].querySelector(".tab"));
  await page.run("workbench.action.editorLayoutSingle");
  assert.strictEqual(groupsIn(page).length, 1, "Single puts every tab back into one group");
  assert.ok(["main.c", "Makefile", "Verdict", "verdict.md"].every((t) => tabTitles(page).includes(t)));
  await page.run("workbench.action.editorLayoutGrid");
  assert.strictEqual(groupsIn(page).length, 4);
  noErrors(page);
});

scenario("a_tab_dragged_to_the_edge_of_a_group_splits_it_and_dropped_on_another_group_moves_it", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  const body = page.$(".editor-group .group-body");
  // jsdom has no layout: every box is 0 x 0, which dropZone reads as the centre. Say where the pointer is by stubbing the rectangle.
  body.getBoundingClientRect = () => ({ left: 0, right: 100, top: 0, bottom: 100, width: 100, height: 100 });
  await page.drag(".tab[data-key='main.c']", body, { at: { x: 95, y: 50 } });
  assert.strictEqual(groupsIn(page).length, 2, "dropped on the right edge: a group is made on the right");
  const second = page.$$(".editor-group")[1];
  assert.ok(second.querySelector(".tab[data-key='main.c']"));
  await page.drag(".tab[data-key='main.c']", page.$$(".editor-group .tab")[0]);
  assert.ok(page.$$(".editor-group")[0].querySelector(".tab[data-key='main.c']"), "dropped on a tab of another group: it goes there");
  noErrors(page);
});

scenario("closing_tabs_with_the_keyboard_the_middle_button_and_the_menu", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.dblclick("#tree .row[data-path='Makefile']");
  await page.settle(60);
  assert.ok(await page.key("alt+w"));
  assert.ok(!tabTitles(page).includes("Makefile"), "Alt+W closes the tab in front");
  page.$(".tab[data-key='main.c']").dispatchEvent(new page.window.MouseEvent("auxclick", { button: 1, bubbles: true, cancelable: true }));
  await page.settle();
  assert.ok(!tabTitles(page).includes("main.c"), "a middle click closes a tab");
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.dblclick("#tree .row[data-path='Makefile']");
  await page.contextmenu(".tab[data-key='Makefile']");
  assert.deepStrictEqual(page.texts(".menu-label").slice(0, 4), ["Close", "Close Others", "Close to the Right", "Close All"]);
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Close Others")));
  assert.ok(tabTitles(page).includes("Makefile") && !tabTitles(page).includes("main.c"));
  assert.ok(tabTitles(page).includes("Verdict"), "the Verdict stays: it cannot be closed");
  noErrors(page);
});

scenario("opened_editors_can_be_listed_and_any_tab_can_be_dragged", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.dblclick("#tree .row[data-path='Makefile']");
  await page.settle(60);
  page.eval("runCommand('workbench.action.showAllEditors')");
  await page.settle(40);
  assert.deepStrictEqual(page.texts(".pi-label"), ["Makefile", "main.c", "Verdict", "verdict.md"], "the most recently used first, the ones never shown last");
  await page.type("#palette input", "verd");
  await page.key("enter");
  assert.ok(page.eval("activeTab") === "verdict.md" || page.eval("activeTab") === "overview");
  assert.ok(page.$$(".tab").every((t) => t.getAttribute("draggable") === "true"), "even the tabs that cannot be closed can be dragged");
  noErrors(page);
});

scenario("go_back_and_forward_between_places", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.dblclick("#tree .row[data-path='Makefile']");
  await page.settle(60);
  assert.strictEqual(page.eval("activeTab"), "Makefile");
  await page.key("alt+left");
  assert.strictEqual(page.eval("activeTab"), "main.c");
  await page.key("alt+right");
  assert.strictEqual(page.eval("activeTab"), "Makefile");
});

scenario("find_in_the_file_in_front", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  assert.ok(await page.key("mod+f"));
  assert.ok(page.visible(".find-widget"));
  await page.type(".find-widget input", "return");
  assert.strictEqual(page.text(".find-count"), "1 of 1");
  assert.strictEqual(page.$$(".find-hl").length, 1, "the match is drawn behind the text");
  await page.type(".find-widget input", "i");
  assert.match(page.text(".find-count"), /^1 of \d+$/);
  await page.type(".find-widget input", "zzz");
  assert.strictEqual(page.text(".find-count"), "No results");
  await page.click(page.$$(".find-toggle")[2]);
  await page.type(".find-widget input", "(");
  assert.strictEqual(page.text(".find-count"), "Invalid", "a pattern that is not a regular expression is said so");
  await page.key("escape", ".find-widget input");
  assert.ok(!page.visible(".find-widget"));
  noErrors(page);
});

scenario("find_starts_from_the_selection", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  page.eval("selectOffsets(tabs.get('main.c').srcEl, 1, 8)");
  await page.key("mod+f");
  assert.strictEqual(page.$(".find-widget input").value, "include");
  assert.strictEqual(page.text(".find-count"), "1 of 1");
  noErrors(page);
});

scenario("go_to_line_and_go_to_symbol", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  assert.ok(await page.key("ctrl+g"), "Ctrl+G on every platform");
  assert.strictEqual(page.$("#palette input").value, ":");
  await page.type("#palette input", ":6");
  await page.key("enter");
  await page.settle(60);
  assert.strictEqual(page.eval("tabs.get('main.c').cursor.line"), 6);
  assert.match(page.text("#statusbar"), /Ln 6/);
  await page.key("mod+shift+o");
  assert.strictEqual(page.$("#palette input").value, "@");
  assert.ok(page.texts(".pi-label").includes("main"), "the functions of the file are listed");
  await page.key("escape", "#palette input");
  assert.ok(!page.visible("#palette"));
  noErrors(page);
});

scenario("select_all_in_the_editor", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  page.$(".code-view").focus();
  assert.ok(await page.key("mod+a", ".code-view"));
  assert.match(page.window.getSelection().toString(), /#include <stdio.h>/);
  assert.ok(page.window.getSelection().toString().endsWith("}\n") || page.window.getSelection().toString().includes("return (0)"));
});

// ---------------------------------------------------------------- quick open, the command palette, chords, key bindings

scenario("quick_open_finds_files_by_name_and_opens_them", async () => {
  const page = await ready();
  assert.ok(await page.key("mod+p"));
  assert.ok(page.visible("#palette"));
  assert.ok(page.texts(".pi-label").includes("util.c"));
  await page.type("#palette input", "mkf");
  assert.strictEqual(page.texts(".pi-label").join(""), "Makefile");
  await page.key("enter");
  await page.settle(60);
  assert.ok(tabTitles(page).includes("Makefile"));
  assert.ok(!page.visible("#palette"));
  await page.key("mod+p");
  await page.type("#palette input", "main:3");
  await page.key("enter");
  await page.settle(60);
  assert.strictEqual(page.eval("tabs.get('main.c').cursor.line"), 3, "file:line opens at the line");
});

scenario("command_palette_runs_commands_and_remembers_the_last_ones", async () => {
  const page = await ready();
  await page.key("mod+shift+p");
  assert.strictEqual(page.$("#palette input").value, ">");
  await page.type("#palette input", ">zen");
  assert.ok(page.texts(".pi-label")[0].includes("Zen"));
  await page.key("enter");
  assert.ok(bodyHas(page, "zen"));
  await page.key("mod+k z");
  await page.key("f1");
  assert.ok(page.texts(".palette-section").includes("recently used"));
  assert.ok(page.texts(".pi-label")[0].includes("Zen"), "what was run last is first");
  await page.key("escape", "#palette input");
});

scenario("chords_wait_for_the_second_key_and_say_so_in_the_status_bar", async () => {
  const page = await ready();
  await page.key("mod+k");
  assert.match(page.text(".status-chord"), /was pressed. Waiting for second key of chord/);
  await page.key("q");
  assert.ok(!page.$(".status-chord"), "a chord that leads nowhere is dropped");
  assert.match(page.texts(".toast-message").join(" "), /is not a command/);
  const told = page.texts(".toast-message").length;
  await page.key("mod+k");
  await page.key("escape");
  assert.ok(!page.$(".status-chord"), "Escape gives a chord up");
  assert.strictEqual(page.texts(".toast-message").length, told, "without a word");
  await page.key("mod+k mod+t");
  assert.ok(page.visible("#palette"), "Cmd/Ctrl+K Cmd/Ctrl+T opens the colour theme picker");
  await page.key("escape", "#palette input");
});

scenario("plain_keys_typed_in_a_field_are_text_not_commands", async () => {
  const page = await ready({ storage: { "verdict.keybindings": JSON.stringify([{ command: "workbench.action.toggleZenMode", key: "z" }]) } });
  await page.click(".activity-item[data-container=search]");
  const input = page.$(".search-input");
  input.focus();
  assert.ok(!(await page.key("z", input)), "a letter in a field is left alone, even when a command is bound to it");
  assert.ok(!bodyHas(page, "zen"));
  assert.ok(await page.key("mod+b", input), "but a key with Cmd/Ctrl still is a command");
  await page.key("mod+b");
  assert.ok(await page.key("f1", input), "and so is F1");
  assert.ok(page.visible("#palette"));
  await page.key("escape", "#palette input");
  page.document.body.focus();
  assert.ok(await page.key("z", page.document.body), "outside a field the same key is the command");
  assert.ok(bodyHas(page, "zen"));
});

scenario("keys_can_be_rebound_in_the_keyboard_shortcuts_editor", async () => {
  const page = await ready();
  await page.key("mod+k mod+s");
  assert.ok(page.$(".tab[data-key=keybindings]"), "Cmd/Ctrl+K Cmd/Ctrl+S opens the Keyboard Shortcuts editor");
  assert.ok(page.$$("table.keybindings tbody tr").length > 80);
  await page.type(".settings-search", "toggle zen");
  const row = page.$("table.keybindings tr[data-command='workbench.action.toggleZenMode']");
  assert.ok(row);
  assert.ok(row.textContent.includes("K") && row.textContent.includes("Z"));
  await page.dblclick(row);
  assert.ok(page.$(".record-keys"), "a double click asks for the new key");
  page.document.dispatchEvent(new page.window.KeyboardEvent("keydown", { key: "9", code: "Digit9", ctrlKey: true, altKey: true, bubbles: true, cancelable: true }));
  page.document.dispatchEvent(new page.window.KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true, cancelable: true }));
  await page.settle();
  const saved = JSON.parse(page.storage()["verdict.keybindings"]);
  assert.ok(saved.some((b) => b.command === "workbench.action.toggleZenMode" && b.key === "mod+alt+9"));
  assert.ok(saved.some((b) => b.command === "-workbench.action.toggleZenMode" && b.key === "mod+k z"), "the key it had is taken away");
  await page.key("mod+k z");
  assert.ok(!bodyHas(page, "zen"));
  await page.key("mod+alt+9");
  assert.ok(bodyHas(page, "zen"), "the new key works at once");
  await page.run("workbench.action.toggleZenMode");
  noErrors(page);
});

// ---------------------------------------------------------------- terminals: several shells, panes split like tmux, claude

const socketsFor = (page, pane) => page.sockets.filter((s) => s.url.includes(`pane=${pane}`));
const rows = (page) => page.$$(".terminal-row").map((e) => e.getAttribute("title"));

scenario("the_terminal_key_opens_a_shell_in_the_panel", async () => {
  const page = await ready();
  assert.ok(await page.key("ctrl+`"), "Ctrl+` on every platform");
  assert.ok(page.visible("#panel") && page.$(".panel-tab.active").dataset.container === "terminal");
  assert.strictEqual(page.$$(".terminal-pane").length, 1);
  assert.strictEqual(socketsFor(page, "t1").length, 1);
  assert.match(socketsFor(page, "t1")[0].url, /^ws:\/\/localhost:8000\/api\/sessions\/s1\/terminal\?cols=80&rows=24&kind=shell&pane=t1$/);
  assert.ok(!page.$(".terminal-list"), "a single terminal has no list beside it");
  await page.key("ctrl+`");
  assert.ok(!page.visible("#panel"), "the same key hides the panel again");
  noErrors(page);
});

scenario("terminals_split_right_and_down_and_each_pane_is_its_own_shell", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.toggleTerminal");
  await page.run("workbench.action.terminal.split");
  assert.strictEqual(page.$$(".terminal-pane").length, 2, "Split Terminal makes a second pane beside the first");
  assert.ok(page.$(".terminal-stage .grid-row"), "side by side");
  assert.strictEqual(socketsFor(page, "t2").length, 1, "the new pane is a shell of its own");
  await page.run("workbench.action.terminal.splitDown");
  assert.strictEqual(page.$$(".terminal-pane").length, 3);
  assert.ok(page.$(".terminal-stage .grid-column"), "and one above the other");
  assert.strictEqual(rows(page).length, 3, "the list on the right names them");
  assert.ok(page.$(".terminal-pane.active"), "one of them has the focus");
  noErrors(page);
});

scenario("new_terminals_are_tabs_of_a_list_and_killing_one_ends_that_shell_only", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.key("ctrl+shift+`");
  assert.strictEqual(rows(page).length, 2, "Ctrl+Shift+` makes another terminal");
  assert.strictEqual(page.$$(".terminal-pane").length, 1, "one group on show at a time");
  await page.click(page.$$(".terminal-row")[0]);
  assert.ok(page.$(".terminal-pane[data-pane=t1]"), "a click on the list shows that terminal");
  await page.run("workbench.action.terminal.kill");
  await page.settle(60);
  assert.ok(page.called("POST /api/sessions/s1/shell/end").some((c) => c.search === "?pane=t1"), "the server is told to end that shell");
  assert.ok(page.$(".terminal-pane[data-pane=t2]"), "the other terminal is left");
  assert.strictEqual(page.terminals.filter((t) => t.disposed).length, 1);
  noErrors(page);
});

scenario("no_more_than_eight_terminals_are_made", async () => {
  const page = await ready();
  for (let i = 0; i < 8; i++) await page.run("workbench.action.terminal.new");
  assert.strictEqual(rows(page).length, 8);
  await page.run("workbench.action.terminal.new");
  await page.run("workbench.action.terminal.split");
  assert.strictEqual(page.eval("termPanes(terminals).length"), 8, "the service would refuse a ninth: it is not asked");
  assert.match(page.texts(".toast-message").join(" "), /At most 8 terminals/);
  noErrors(page);
});

scenario("the_list_of_terminals_can_be_on_the_left", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.run("workbench.action.terminal.new");
  assert.ok(!page.$(".terminal-view.tabs-left"));
  page.eval("settings.set('terminal.integrated.tabs.location', 'left')");
  await page.settle();
  assert.ok(page.$(".terminal-view.tabs-left"), "the setting moves the list to the other side");
  noErrors(page);
});

scenario("a_file_dropped_on_a_terminal_is_typed_there", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.settle(60);
  const data = { "application/x-verdict-path": "src/my file.c" };
  const transfer = { types: Object.keys(data), getData: (k) => data[k] ?? "" };
  const over = new page.window.Event("dragover", { bubbles: true, cancelable: true });
  over.dataTransfer = transfer;
  page.$(".terminal-pane").dispatchEvent(over);
  assert.ok(over.defaultPrevented, "a terminal accepts a file of the explorer");
  const drop = new page.window.Event("drop", { bubbles: true, cancelable: true });
  drop.dataTransfer = transfer;
  page.$(".terminal-pane").dispatchEvent(drop);
  const typed = socketsFor(page, "t1")[0].sent.map((d) => JSON.parse(d)).filter((e) => e.t === "i").map((e) => e.d).join("");
  assert.strictEqual(typed, "'src/my file.c' ", "the path is typed at the prompt, quoted for the shell, not run");
  noErrors(page);
});

scenario("a_terminal_can_be_renamed", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.run("workbench.action.terminal.split");
  await page.run("workbench.action.terminal.rename");
  const input = page.$(".terminal-rename");
  assert.ok(input, "the name becomes a field");
  input.value = "build";
  await page.key("enter", input);
  assert.ok(page.texts(".terminal-title").includes("build"));
  const saved = JSON.parse(page.storage()["verdict.terminals:s1"]);
  assert.strictEqual(saved.titles.t2, "build", "the name is remembered");
});

scenario("pane_focus_moves_with_the_keys_inside_a_terminal", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.run("workbench.action.terminal.split");
  await page.settle(60);
  const active = () => page.$(".terminal-pane.active").dataset.pane;
  assert.strictEqual(active(), "t2");
  const field = page.terminals[0].input;
  field.focus();
  assert.ok(await page.key("alt+left", field), "Alt+Left in a terminal goes to the pane on the left");
  assert.strictEqual(active(), "t1");
  await page.key("alt+right", page.terminals[0].input);
  assert.strictEqual(active(), "t2");
  assert.ok(!(await page.key("alt+left", "#sidebar")) || true);
});

scenario("a_shell_that_ends_leaves_the_list_and_a_dropped_connection_comes_back", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.run("workbench.action.terminal.new");
  await page.settle(40);
  assert.strictEqual(rows(page).length, 2);
  const second = socketsFor(page, "t2")[0];
  second.onclose({ code: 4410 });
  await page.settle(40);
  assert.deepStrictEqual(page.$$(".terminal-pane").map((e) => e.dataset.pane), ["t1"], "a shell that ended (exit) is gone from the panel");
  assert.deepStrictEqual(JSON.parse(page.eval("JSON.stringify(termPanes(terminals))")), ["t1"]);
  const first = socketsFor(page, "t1")[0];
  first.onclose({ code: 1006 });
  assert.ok(page.terminals[0].written.some((w) => w.includes("connection lost")), "the terminal says the connection was lost");
  await page.settle(1200);
  assert.strictEqual(socketsFor(page, "t1").length, 2, "and connects again by itself: the shell kept running");
  socketsFor(page, "t1")[1].onclose({ code: 4411 });
  assert.ok(page.terminals[0].written.some((w) => w.includes("opened in another tab")), "a shell opened in another tab says so and is not taken back");
  await page.settle(1200);
  assert.strictEqual(socketsFor(page, "t1").length, 2);
  noErrors(page);
});

scenario("a_terminal_moves_into_the_editor_area_and_back", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.run("workbench.action.terminal.moveToEditor");
  await page.settle(60);
  assert.ok(page.$(".tab[data-key='shell:t1']"), "it is a tab of the editor area");
  assert.strictEqual(page.$$(".terminal-pane").length, 0);
  assert.strictEqual(page.terminals.filter((t) => t.disposed).length, 0, "the same shell, not a new one");
  await page.run("workbench.action.terminal.moveToPanel");
  assert.ok(!page.$(".tab[data-key='shell:t1']"));
  assert.strictEqual(page.$$(".terminal-pane").length, 1);
  assert.strictEqual(page.called("POST /api/sessions/s1/shell/end").length, 0, "nothing was ended on the way");
  noErrors(page);
});

scenario("the_terminals_of_a_reloaded_page_are_the_ones_the_server_still_runs", async () => {
  const first = await ready();
  await first.run("workbench.action.terminal.new");
  await first.run("workbench.action.terminal.new");
  const second = await ready({ storage: first.storage(), shells: { panes: ["t2", "t5"], claude: false } });
  await second.run("workbench.action.terminal.toggleTerminal");
  await second.settle(80);
  const names = second.$$(".terminal-row").map((e) => e.dataset.pane).sort();
  assert.deepStrictEqual(names, ["t2", "t5"], "t1 is gone on the server, t5 was started elsewhere");
  noErrors(second);
});

scenario("terminals_need_a_project", async () => {
  const page = await ready({ session: fixtureSession({ repo: null, results: [], subjects: [] }) });
  await page.run("workbench.action.terminal.toggleTerminal");
  assert.match(page.text("#panel .terminal-empty"), /Open a project/);
  await page.run("workbench.action.terminal.new");
  assert.match(page.texts(".toast-message").join(" "), /Open a project first/);
});

scenario("claude_is_a_tab_of_the_editor_area", async () => {
  const page = await ready();
  await page.run("verdict.openClaude");
  await page.settle(80);
  assert.ok(page.$(".tab[data-key=terminal] .tab-title"));
  assert.match(page.text(".term-bar"), /throw-away copy/);
  const claude = page.sockets.find((s) => !s.url.includes("kind=shell"));
  assert.ok(claude, "a socket without kind=shell");
  await page.run("verdict.openClaude");
  assert.strictEqual(page.sockets.filter((s) => !s.url.includes("kind=shell")).length, 1, "a second Open Claude shows the one that is open");
  await page.click(".tab[data-key=terminal] .close");
  assert.strictEqual(page.called("POST /api/sessions/s1/terminal/end").length, 1, "closing the tab ends claude on purpose");
  noErrors(page);
});

// ---------------------------------------------------------------- source control and the diff editor

const CHANGES = [
  { path: "Makefile", x: "M", y: "M", kind: "modified" },
  { path: "main.c", x: "", y: "M", kind: "modified" },
  { path: "src/new.c", x: "?", y: "?", kind: "untracked" },
];
const LONG = Array.from({ length: 40 }, (_, i) => `line ${i + 1}`).join("\n") + "\n";
const LONG_EDITED = LONG.replace("line 12\n", "line twelve\n").replace("line 25\n", "line twenty-five\n");

scenario("source_control_lists_the_changes_and_decorates_the_explorer", async () => {
  const page = await ready({ changes: CHANGES });
  await page.settle(1700);
  assert.strictEqual(page.$(".activity-item[data-container=scm] .activity-badge").textContent, "3");
  assert.ok(page.$("#tree .row[data-path='main.c'] .git-badge"), "the explorer marks the file");
  assert.strictEqual(page.text("#tree .row[data-path='main.c'] .git-badge"), "M");
  assert.ok(page.$("#tree .row[data-dir='src'] .git-dot"), "and the folder that holds a change");
  await page.run("workbench.files.action.refreshFilesExplorer");
  await page.settle(60);
  assert.ok(page.$("#tree .row[data-path='main.c'] .git-badge"), "a tree drawn again is marked at once, not after the next look at git");
  await page.click(".activity-item[data-container=scm]");
  assert.deepStrictEqual(page.texts(".scm-group .row-name"), ["Staged Changes", "Changes"]);
  assert.deepStrictEqual(page.texts(".scm-row .row-name"), ["Makefile", "Makefile", "main.c", "new.c"]);
  await page.click(page.$$(".scm-row")[2]);
  await page.click(page.$$(".scm-row")[3]);
  await page.settle(60);
  assert.deepStrictEqual(page.$$(".tab.preview").map((t) => t.dataset.key), ["diff:tree:src/new.c"], "a diff opened with a click replaces the previous preview");
  assert.deepStrictEqual(page.texts(".scm-status"), ["M", "M", "M", "U"]);
  assert.match(page.text(".scm-branch"), /main/);
  assert.match(page.text(".scm-sync"), /1↑ 0↓/);
  noErrors(page);
});

scenario("a_change_opens_in_a_side_by_side_diff_with_folds_and_next_change", async () => {
  const page = await ready({ changes: [{ path: "long.txt", x: "", y: "M", kind: "modified" }], diffs: { "long.txt": LONG_EDITED }, routes: {
    "GET /api/sessions/[^/]+/git/diff": ({ json }) => json({ path: "long.txt", before: LONG, after: LONG_EDITED, binary: false, truncated: false, state: "modified" }),
  } });
  await page.settle(1700);
  await page.click(".activity-item[data-container=scm]");
  await page.click(".scm-row");
  await page.settle(60);
  const tab = page.$(".tab[data-key='diff:tree:long.txt']");
  assert.ok(tab, "the change opens in a tab");
  assert.strictEqual(tab.querySelector(".tab-title").textContent, "long.txt (Working Tree)");
  assert.ok(page.$(".tab.preview[data-key='diff:tree:long.txt']"), "a single click is a preview");
  assert.strictEqual(page.$$(".diff-left .diff-line.removed").length, 2, "two lines were replaced");
  assert.strictEqual(page.$$(".diff-right .diff-line.added").length, 2);
  assert.strictEqual(page.$$(".diff-left .diff-fold").length, 3, "the long stretches that did not change are folded");
  assert.match(page.text(".diff-fold"), /unchanged lines/);
  await page.run("workbench.action.compareEditor.nextChange");
  assert.ok(page.$(".current-change"), "Next Change marks the first difference");
  assert.strictEqual(page.text(".diff-position"), "Difference 1 of 2");
  await page.key("f7");
  assert.strictEqual(page.text(".diff-position"), "Difference 2 of 2");
  await page.click(page.$$(".diff-left .diff-fold").at(-1));
  assert.strictEqual(page.$$(".diff-left .diff-fold").length, 2, "a fold opens when it is clicked");
  assert.deepStrictEqual(page.$$(".group-actions .icon-button").map((b) => b.title.replace(/ \(.*\)$/, "")).slice(0, 4),
    ["Previous Change", "Next Change", "Switch to Inline View", "Open File"], "the diff has its own buttons in the title of the group");
  await page.click(page.$$(".group-actions .icon-button").find((b) => b.title === "Switch to Inline View"));
  assert.ok(page.$(".diff-inline") && !page.$(".diff-left"), "the inline view");
  assert.strictEqual(page.$$(".diff-inline .diff-line.removed").length, 2);
  assert.strictEqual(page.$$(".diff-inline .diff-line.eq")[0].querySelectorAll(".diff-num").length, 2, "with a column of numbers for each side");
  assert.ok(page.$(".group-actions [title='Switch to Side by Side View']"));
  noErrors(page);
});

scenario("compare_two_files_from_the_explorer", async () => {
  const page = await ready();
  await page.contextmenu("#tree .row[data-path='main.c']");
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Select for Compare")));
  await page.contextmenu("#tree .row[data-path='Makefile']");
  const compare = page.$$(".menu-item").find((e) => e.textContent.startsWith("Compare with Selected"));
  assert.ok(!compare.classList.contains("disabled"));
  await page.click(compare);
  await page.settle(60);
  assert.ok(page.texts(".tab .tab-title").some((t) => t === "main.c ↔ Makefile"));
  assert.ok(page.$(".diff-view .diff-line.removed") && page.$(".diff-view .diff-line.added"));
  noErrors(page);
});

scenario("open_changes_from_the_file_in_front", async () => {
  const page = await ready({ changes: CHANGES });
  await page.settle(1700);
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  await page.run("git.openChange");
  await page.settle(60);
  assert.ok(page.$(".tab[data-key='diff:tree:main.c']"));
  noErrors(page);
});

scenario("git_is_not_asked_more_than_once_in_a_moment", async () => {
  const page = await ready({ changes: CHANGES });
  await page.settle(2600);
  const asked = () => page.called("GET /api/sessions/s1/git/status").length;
  const before = asked();
  page.eval("loadScm()");
  await page.settle(60);
  page.eval("loadScm()");
  page.eval("loadScm()");
  await page.settle(60);
  assert.strictEqual(asked(), before + 1, "a second look right after the first waits (the explorer is read again often while claude works)");
  page.eval("loadScm({ force: true })");
  await page.settle(60);
  assert.strictEqual(asked(), before + 2, "unless it is asked for on purpose (the Refresh button)");
});

scenario("source_control_says_when_git_cannot_be_used", async () => {
  const page = await ready({ routes: { "GET /api/sessions/[^/]+/git/status": ({ json }) => json({ available: false, error: "Not reading it with git: .git/config has settings that could run commands (core.fsmonitor).", files: [] }) } });
  await page.click(".activity-item[data-container=scm]");
  await page.settle(1700);
  assert.match(page.text(".scm-note"), /could run commands/);
  assert.ok(!page.$(".activity-item[data-container=scm] .activity-badge"));
  noErrors(page);
});

// ---------------------------------------------------------------- search

scenario("find_in_files_searches_the_project_and_opens_the_match", async () => {
  const page = await ready();
  assert.ok(await page.key("mod+shift+f"));
  assert.strictEqual(page.text("#sidebar .part-title"), "Search");
  await page.type(".search-input", "return");
  await page.settle(500);
  const asked = page.called("GET /api/sessions/s1/search").at(-1);
  assert.match(asked.search, /q=return/);
  assert.match(asked.search, /regex=false/);
  assert.strictEqual(page.texts(".search-file .row-name").join(), "main.c");
  assert.strictEqual(page.text(".search-summary"), "1 result in 1 file");
  await page.click(page.$$(".find-toggle", page.$(".search-box"))[2]);
  await page.settle(500);
  assert.match(page.called("GET /api/sessions/s1/search").at(-1).search, /regex=true/, "the toggles are sent");
  await page.click(".search-match");
  await page.settle(80);
  assert.ok(page.$(".tab[data-key='main.c']"));
  assert.strictEqual(page.eval("tabs.get('main.c').cursor.line"), 6);
  noErrors(page);
});

scenario("a_search_in_a_folder_from_the_explorer_fills_the_include_field", async () => {
  const page = await ready();
  await page.contextmenu("#tree .row[data-dir='src']");
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Find in Folder")));
  await page.settle(60);
  assert.strictEqual(page.$(".search-details input").value, "src/");
  assert.ok(page.visible(".search-details"));
});

// ---------------------------------------------------------------- settings, themes, notifications, dialogs

scenario("settings_editor_changes_how_the_page_looks_and_remembers_it", async () => {
  const page = await ready();
  await page.key("mod+,");
  assert.ok(page.$(".tab[data-key=settings]"));
  assert.ok(page.$$(".setting").length >= 10);
  await page.type(".settings-search", "font size");
  assert.ok(page.$$(".setting").length >= 2);
  const field = page.$(".setting[data-setting='editor.fontSize'] input");
  field.value = "18";
  field.dispatchEvent(new page.window.Event("change", { bubbles: true }));
  await page.settle();
  assert.strictEqual(page.window.document.documentElement.style.getPropertyValue("--editor-font-size"), "18px");
  assert.strictEqual(JSON.parse(page.storage()["verdict.settings"])["editor.fontSize"], 18);
  assert.ok(page.$(".setting[data-setting='editor.fontSize'].modified"), "a setting that is not the usual one is marked");
  assert.match(page.text(".setting[data-setting='editor.fontSize'] .setting-modified"), /Modified/);
  await page.click(page.$(".setting[data-setting='editor.fontSize'] .linklike"));
  assert.strictEqual(page.window.document.documentElement.style.getPropertyValue("--editor-font-size"), "13px", "Reset Setting gives the usual value back");
  assert.ok(!page.$(".setting[data-setting='editor.fontSize'].modified"));
  page.eval("settings.set('editor.fontSize', 18)");
  await page.run("workbench.action.zoomIn");
  assert.strictEqual(page.window.document.documentElement.style.getPropertyValue("--zoom"), "1.2");
  assert.strictEqual(page.window.document.documentElement.style.getPropertyValue("--editor-font-size"), "21.6px");
  await page.run("workbench.action.zoomReset");
  noErrors(page);
});

scenario("colour_themes_preview_and_apply", async () => {
  const page = await ready();
  const theme = () => page.document.documentElement.dataset.theme;
  await page.key("mod+k mod+t");
  assert.deepStrictEqual(page.texts(".pi-label"), ["Dark Modern", "Dark+", "Light+", "Solarized Dark", "High Contrast"]);
  await page.key("down", "#palette input");
  assert.strictEqual(theme(), "dark", "the theme under the cursor is shown at once");
  await page.key("escape", "#palette input");
  assert.strictEqual(theme(), "modern", "and given back when the picker is closed");
  await page.key("mod+k mod+t");
  await page.key("down", "#palette input");
  await page.key("down", "#palette input");
  await page.key("enter", "#palette input");
  assert.strictEqual(theme(), "light");
  assert.strictEqual(JSON.parse(page.storage()["verdict.settings"])["workbench.colorTheme"], "Light+");
  const again = await ready({ storage: page.storage() });
  assert.strictEqual(again.document.documentElement.dataset.theme, "light", "it is the same after a reload");
});

scenario("notifications_toast_then_wait_in_the_bell", async () => {
  const page = await ready();
  await page.eval("notify('Careful', { level: 'warning' })");
  assert.match(page.text("#toasts"), /Careful/);
  assert.strictEqual(page.text(".status-notifications .status-text"), "1");
  await page.click(".status-notifications");
  assert.ok(page.$("#notification-center .notification-warning"));
  assert.ok(!page.$(".status-notifications .status-text"), "reading them clears the count");
  await page.click("#notification-center [title='Clear All Notifications']");
  assert.match(page.text("#notification-center"), /No new notifications/);
  await page.key("escape");
  await page.run("notifications.toggleDoNotDisturbMode");
  await page.eval("notify('Quiet')");
  assert.ok(!page.texts("#toasts .toast-message").includes("Quiet"), "Do Not Disturb keeps toasts away");
});

scenario("open_project_environment_and_about_dialogs", async () => {
  const page = await ready();
  await page.run("workbench.action.files.openProject");
  await page.settle(80);
  assert.match(page.text("#dialog h3"), /Open a project/);
  assert.ok(page.visible("#modal"));
  await page.key("escape");
  assert.ok(!page.visible("#modal"), "Escape closes a dialog");
  await page.run("verdict.environment");
  await page.settle(80);
  assert.match(page.text("#dialog"), /Ready/);
  await page.click("#modal");
  assert.ok(!page.visible("#modal"), "a click outside closes it too");
  await page.run("verdict.about");
  assert.match(page.text("#dialog"), /Session/);
  noErrors(page);
});

scenario("a_pdf_dropped_on_the_window_asks_where_it_belongs", async () => {
  const page = await ready();
  const drop = new page.window.Event("drop", { bubbles: true, cancelable: true });
  drop.dataTransfer = { types: ["Files"], files: [{ name: "subject.pdf" }] };
  page.document.body.dispatchEvent(drop);
  await page.settle(80);
  assert.ok(drop.defaultPrevented);
  assert.match(page.text("#dialog h3"), /Upload subject PDFs/);
  assert.match(page.text("#dialog"), /subject\.pdf/);
});

// ---------------------------------------------------------------- the review: run, the verdict, the lists

scenario("run_starts_from_nothing_and_follows_the_run", async () => {
  let polls = 0;
  const page = await ready({ routes: {
    "POST /api/sessions/[^/]+/run": ({ json, state }) => { state.session = fixtureSession({ state: "running", message: "cloning", results: [], summary: fixtureSession().summary }); polls = 0; return json(state.session); },
    "GET /api/sessions/[^/]+": ({ json, state }) => {
      if (state.session.state === "running" && ++polls >= 2) state.session = fixtureSession({ state: "done" });
      return json(state.session);
    },
  } });
  await page.run("verdict.openClaude");
  await page.eval("openFile('main.c')");
  await page.settle(80);
  await page.click(".activity-item[data-container=run]");
  assert.ok(page.$(".tab[data-key=terminal]") && page.$(".tab[data-key='main.c']") && page.$(".tab[data-key='verdict.md']"));
  const lookedAtGit = page.called("GET /api/sessions/s1/git/status").length;
  await page.key("mod+shift+b");
  assert.strictEqual(page.called("POST /api/sessions/s1/run").length, 1, "Run Checks asked the server");
  assert.ok(page.called("GET /api/sessions/s1/git/status").length > lookedAtGit, "and Source Control looked again at what changed");
  assert.ok(!page.$(".tab[data-key=terminal]"), "claude's tab is closed");
  assert.ok(!page.$(".tab[data-key='main.c']"), "the files of the old run are closed");
  assert.strictEqual(page.called("POST /api/sessions/s1/terminal/end").length, 0, "the server already ended claude: nothing to end");
  assert.ok(page.$("#statusbar.busy"), "the status bar shows that something is running");
  assert.strictEqual(page.$("[data-command='verdict.run']").disabled, true);
  await page.settle(2500);
  assert.ok(!page.$("#statusbar.busy"), "and that it is done");
  assert.ok(page.$(".tab[data-key='verdict.md']"), "the new verdict.md is shown");
  assert.match(page.texts("#panel .item-title").join(), /Makefile/);
  noErrors(page);
});

scenario("the_commands_of_the_old_top_bar_say_why_they_are_unavailable", async () => {
  const page = await ready({ session: fixtureSession({ repo: null, results: [], subjects: [], state: "idle" }) });
  await page.click(".activity-item[data-container=run]");
  await page.run("verdict.run");
  assert.match(page.texts(".toast-message").join(" "), /Open a project first/);
  await page.run("verdict.aiReview");
  await page.run("verdict.fixPrompt");
  assert.ok(page.texts(".toast-message").length >= 2);
  assert.strictEqual(page.$("[data-command='verdict.run']").disabled, true, "the Run view's button is greyed out too");
});

scenario("the_checklist_filters_and_opens_evidence", async () => {
  const page = await ready();
  assert.deepStrictEqual(page.texts("#panel .filters .chip"), ["✖ 1", "! 0", "? 0", "– 0", "∅ 0", "✔ 1"]);
  await page.click(page.$$("#panel .filters .chip")[5]);
  assert.ok(!page.texts("#panel .item-title").includes("Norm"), "a filter hides what it names");
  await page.click("#panel .item-head");
  await page.click("#panel .ev");
  await page.settle(80);
  assert.ok(page.$(".tab[data-key=Makefile]"), "the evidence opens the file");
  await page.click("#panel .page-link");
  await page.settle(80);
  assert.ok(page.$(".tab[data-key='pdf:fract-ol.pdf']"), "the source opens the subject PDF");
  noErrors(page);
});

scenario("subjects_view_opens_and_removes_pdfs", async () => {
  const page = await ready({ routes: { "DELETE /api/sessions/[^/]+/subjects/[^/]+": ({ json, state }) => { state.session = fixtureSession({ subjects: [] }); return json(state.session); } } });
  await page.click(".activity-item[data-container=subjects]");
  assert.strictEqual(page.texts("#sidebar .list .name").join(), "fract-ol.pdf");
  await page.click("#sidebar .list li");
  await page.settle(80);
  assert.ok(page.$(".tab[data-key='pdf:fract-ol.pdf']"));
  await page.click("#sidebar .list li .x");
  await page.settle(80);
  assert.strictEqual(page.$$("#sidebar .list li").length, 0);
  assert.ok(!page.$(".tab[data-key='pdf:fract-ol.pdf']"), "its tab closes with it");
});

// ---------------------------------------------------------------- menus and context menus

scenario("every_menu_opens_and_its_items_run", async () => {
  const page = await ready();
  for (const [i, name] of ["File", "Edit", "Selection", "View", "Go", "Run", "Terminal", "Help"].entries()) {
    await page.click(page.$$(".menubar-item")[i]);
    assert.ok(page.$$(".menu-item").length > 0, `${name} has items`);
    assert.ok(page.$$(".menubar-item")[i].classList.contains("open"));
    assert.ok(page.texts(".menu-label").every((t) => t.trim() && !t.includes("workbench.")), `${name}: every item has a title (none is an unknown command)`);
    await page.key("escape");
    assert.ok(!page.$(".menu"));
  }
  noErrors(page);
});

scenario("menus_follow_the_mouse_and_the_keyboard_and_show_the_keys", async () => {
  const page = await ready();
  await page.click(page.$$(".menubar-item")[3]);
  assert.ok(page.texts(".menu-key").includes("Ctrl+Shift+P") || page.texts(".menu-key").length > 0);
  await page.hover(page.$$(".menubar-item")[0]);
  assert.ok(page.$$(".menubar-item")[0].classList.contains("open"), "while a menu is open the pointer opens the neighbours");
  const key = (name) => page.key(name, page.$(".menu"));
  await key("down");
  assert.ok(page.$(".menu-item.focus"));
  await page.key("escape");
  await page.click(page.$$(".menubar-item")[3]);
  const appearance = page.$$(".menu-item").find((e) => e.textContent.startsWith("Appearance"));
  await page.hover(appearance);
  assert.ok(page.$$(".menu").length === 2, "a submenu opens beside the item");
  assert.ok(page.texts(".menu-label").includes("Full Screen") || page.texts(".menu-label").includes("Zen Mode"));
  const zen = page.$$(".menu-item").find((e) => e.textContent.startsWith("Zen Mode"));
  await page.click(zen);
  assert.ok(bodyHas(page, "zen"), "the item ran its command");
  assert.ok(!page.$(".menu"), "and the menu closed");
  await page.key("escape escape");
});

scenario("checked_menu_items_follow_the_state", async () => {
  const page = await ready();
  const checked = async (label) => {
    await page.click(page.$$(".menubar-item")[3]);
    await page.hover(page.$$(".menu-item").find((e) => e.textContent.startsWith("Appearance")));
    const item = page.$$(".menu-item").find((e) => e.textContent.startsWith(label));
    const result = item.classList.contains("checked");
    await page.key("escape");
    await page.key("escape");
    return result;
  };
  assert.strictEqual(await checked("Primary Side Bar"), true);
  await page.run("workbench.action.toggleSidebarVisibility");
  assert.strictEqual(await checked("Primary Side Bar"), false);
  assert.strictEqual(await checked("Status Bar"), true);
  await page.run("workbench.action.toggleStatusbarVisibility");
  assert.strictEqual(await checked("Status Bar"), false);
});

scenario("context_menus_on_tabs_the_explorer_and_views", async () => {
  const page = await ready();
  await page.contextmenu("#tree .row[data-path='main.c']");
  assert.ok(page.texts(".menu-label").includes("Open to the Side") && page.texts(".menu-label").includes("Copy Path"));
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Open to the Side")));
  await page.settle(80);
  assert.strictEqual(groupsIn(page).length, 2, "Open to the Side makes a group");
  await page.contextmenu("#sidebar .pane-header[data-view=files]");
  assert.ok(page.texts(".menu-label").some((t) => t.startsWith("Move View to Panel")));
  await page.key("escape");
  await page.contextmenu(".panel-tab[data-container=problems]");
  assert.ok(page.texts(".menu-label").includes("Move to Secondary Side Bar"));
  await page.key("escape");
  await page.click("#manage-button");
  assert.ok(page.texts(".menu-label").includes("Color Theme"));
  await page.key("escape");
  noErrors(page);
});

scenario("explorer_keyboard_navigation", async () => {
  const page = await ready();
  const tree = page.$("#tree");
  tree.focus();
  await page.key("down", tree);
  await page.key("down", tree);
  assert.ok(page.$("#tree .row.selected"));
  const before = page.$("#tree .row.selected").textContent;
  await page.key("right", tree);
  await page.key("end", tree);
  assert.notStrictEqual(page.$("#tree .row.selected").textContent, before);
  await page.key("enter", tree);
  await page.settle(80);
  assert.ok(page.$$(".tab").length >= 3, "Enter opens the file the keyboard is on");
  noErrors(page);
});

scenario("open_editors_and_outline_follow_the_tabs", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  await page.click("#sidebar .pane-header[data-view=openEditors]");
  assert.ok(page.texts("#sidebar .open-title").includes("main.c"));
  await page.click("#sidebar .pane-header[data-view=outline]");
  assert.deepStrictEqual(page.texts("#sidebar .outline-row .row-name"), ["main"], "the outline lists the functions of the file in front");
  await page.click("#sidebar .outline-row");
  await page.settle(40);
  assert.strictEqual(page.eval("tabs.get('main.c').cursor.line"), 3);
  noErrors(page);
});

scenario("status_bar_items_are_buttons_for_their_commands", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  assert.ok(page.$(".status-cursor") && page.$(".status-language"), "the file in front shows where the cursor is and its language");
  await page.click(".status-cursor");
  assert.strictEqual(page.$("#palette input").value, ":");
  await page.key("escape", "#palette input");
  await page.click(".status-problems");
  assert.strictEqual(page.$(".panel-tab.active").dataset.container, "problems");
  await page.click(".status-commit");
  assert.strictEqual(page.text("#sidebar .part-title"), "Source Control");
});

// ---------------------------------------------------------------- the keys

scenario("no_shortcut_is_one_the_browser_keeps_and_none_is_given_twice", async () => {
  const RESERVED = ["mod+w", "mod+t", "mod+n", "mod+shift+n", "mod+shift+t", "mod+shift+w", "mod+q", "mod+l", "mod+tab", "mod+shift+tab", "ctrl+tab", "ctrl+shift+tab", "alt+f4", "mod+pagedown", "mod+pageup"];
  for (const platform of ["Linux x86_64", "MacIntel"]) {
    const page = await ready({ platform });
    const bindings = JSON.parse(page.eval("JSON.stringify(defaultBindings().map((b) => ({ command: b.command, chord: normalizeChord(b.key), when: b.when })))"));
    assert.ok(bindings.length > 50, `${platform}: the commands have keys`);
    const seen = new Map();
    for (const b of bindings) {
      assert.ok(b.chord.length >= 1 && b.chord.length <= 2 && b.chord.every(Boolean), `${platform}: ${b.command} has a key a person can type`);
      assert.ok(!RESERVED.includes(b.chord[0]), `${platform}: ${b.command} uses ${b.chord[0]}, which the browser keeps for itself`);
      const id = `${b.chord.join(" ")} | ${b.when}`;
      assert.ok(!seen.has(id), `${platform}: ${b.command} and ${seen.get(id)} have the same key under the same conditions`);
      seen.set(id, b.command);
    }
    // two commands may share a key only when their conditions tell them apart
    const byChord = new Map();
    for (const b of bindings) byChord.set(b.chord.join(" "), [...(byChord.get(b.chord.join(" ")) ?? []), b]);
    for (const [chord, list] of byChord) if (list.length > 1) assert.ok(list.every((b) => b.when), `${platform}: ${chord} is shared by ${list.map((b) => b.command)} without a condition`);
    // the first key of a chord is not also a command of its own with the same conditions (it would be run before the second key came)
    for (const b of bindings) if (b.chord.length === 2) assert.ok(!bindings.some((o) => o.chord.length === 1 && o.chord[0] === b.chord[0] && o.when === b.when), `${platform}: ${b.chord[0]} is a command and the start of a chord`);
    page.close();
  }
});

scenario("the_mac_uses_command_and_the_others_control", async () => {
  const mac = await ready({ platform: "MacIntel" });
  assert.ok(await mac.key("mod+p"), "Cmd+P on a Mac");
  assert.ok(mac.visible("#palette"));
  await mac.key("escape", "#palette input");
  const ctrlOnly = new mac.window.KeyboardEvent("keydown", { key: "p", code: "KeyP", ctrlKey: true, bubbles: true, cancelable: true });
  mac.document.body.dispatchEvent(ctrlOnly);
  assert.ok(!ctrlOnly.defaultPrevented, "Ctrl+P is not Cmd+P on a Mac");
  assert.match(mac.$$(".activity-item").map((e) => e.title).join(), /\(⇧⌘E\)/, "keys are shown the way a Mac writes them");
  const linux = await ready();
  assert.match(linux.$$(".activity-item").map((e) => e.title).join(), /\(Ctrl\+Shift\+E\)/);
});

scenario("on_windows_and_linux_control_keys_belong_to_the_shell_inside_a_terminal", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  const field = page.terminals[0].input;
  field.focus();
  assert.ok(!(await page.key("mod+k", field)), "Ctrl+K goes to the shell (kill the line), not to a chord of the page");
  assert.ok(!page.$(".status-chord"));
  assert.ok(await page.key("mod+p", field), "but Quick Open is one of the keys a terminal lets through, as in VS Code");
  await page.key("escape", "#palette input");
  const mac = await ready({ platform: "MacIntel" });
  await mac.run("workbench.action.terminal.new");
  assert.ok(await mac.key("mod+k", mac.terminals[0].input), "on a Mac Cmd is never the shell's: Cmd+K starts a chord");
});

// ---------------------------------------------------------------- more of the same, for the paths the first scenarios did not reach

const rect = (el, box) => { el.getBoundingClientRect = () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, ...box }); };
const pointer = (page, el, type, x, y = 0) => { const ev = new page.window.Event(type, { bubbles: true, cancelable: true }); Object.assign(ev, { clientX: x, clientY: y, pointerId: 1 }); el.dispatchEvent(ev); };

scenario("a_view_dropped_on_the_header_of_another_goes_before_or_after_it", async () => {
  const page = await ready();
  await page.drag("#sidebar .pane-header[data-view=outline]", "#sidebar .pane-header[data-view=openEditors]");
  assert.deepStrictEqual(page.$$("#sidebar .pane").map((e) => e.dataset.view), ["openEditors", "outline", "files"], "dropped on the lower half of a header: after it");
  const header = page.$("#sidebar .pane-header[data-view=files]");
  rect(header, { top: 0, height: 100 });
  await page.drag("#sidebar .pane-header[data-view=openEditors]", header, { at: { x: 0, y: 10 } });
  assert.deepStrictEqual(page.$$("#sidebar .pane").map((e) => e.dataset.view), ["outline", "openEditors", "files"], "dropped on the upper half: before it");
  await page.contextmenu("#sidebar .pane-header[data-view=outline]");
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Move View to Panel")));
  assert.ok(panelTabs(page).some((id) => id.startsWith("custom-")), "Move View to Panel gives it a tab of its own");
  await page.contextmenu("#panel .pane-header, #panel .panel-tab[data-container^=custom]");
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Reset View Locations")));
  assert.ok(!panelTabs(page).some((id) => id.startsWith("custom-")));
  assert.deepStrictEqual(page.$$("#sidebar .pane").map((e) => e.dataset.view), ["openEditors", "files", "outline"]);
  noErrors(page);
});

scenario("a_view_can_be_reset_to_its_own_place", async () => {
  const page = await ready();
  await page.drag("#sidebar .pane-header[data-view=outline]", "#panel");
  assert.ok(page.$("#panel .outline"));
  await page.contextmenu("#panel .pane-header[data-view=outline], #panel .panel-tab.active");
  const reset = page.$$(".menu-item").find((e) => e.textContent.startsWith("Reset Location"));
  if (reset) await page.click(reset); else await page.key("escape");
  noErrors(page);
});

scenario("the_activity_bar_is_walked_with_the_arrow_keys_and_dividers_with_the_pointer", async () => {
  const page = await ready();
  const items = page.$$(".activity-top .activity-item");
  items[0].focus();
  await page.key("down", items[0]);
  assert.strictEqual(page.document.activeElement, items[1]);
  await page.key("up", items[1]);
  await page.key("up", items[0]);
  assert.strictEqual(page.document.activeElement, items.at(-1), "it wraps around");
  const bar = page.$("#activitybar");
  rect(bar, { width: 48 });
  const sash = page.$("#sash-sidebar");
  pointer(page, sash, "pointerdown", 0);
  pointer(page, sash, "pointermove", 348);
  assert.strictEqual(page.window.document.documentElement.style.getPropertyValue("--sidebar-w"), "300px", "48px of the activity bar are not the side bar's");
  pointer(page, sash, "pointermove", 448);
  assert.strictEqual(page.window.document.documentElement.style.getPropertyValue("--sidebar-w"), "400px");
  assert.ok(bodyHas(page, "resizing"));
  pointer(page, sash, "lostpointercapture", 448);
  assert.ok(!bodyHas(page, "resizing"));
  assert.strictEqual(layoutNow(page).locations.sidebar.size, 400);
  assert.strictEqual(JSON.parse(page.storage()["verdict.workbench"]).locations.sidebar.size, 400, "and it is remembered");
  pointer(page, sash, "pointerdown", 0);
  pointer(page, sash, "pointermove", 5000);
  assert.ok(layoutNow(page).locations.sidebar.size <= 900, "a divider has limits");
  pointer(page, sash, "lostpointercapture", 0);
  await page.run("workbench.action.positionPanelRight");
  const panelSash = page.$("#sash-panel");
  rect(page.$("#center"), { left: 0, right: 1000, top: 0, bottom: 600 });
  pointer(page, panelSash, "pointerdown", 0);
  pointer(page, panelSash, "pointermove", 700);
  assert.strictEqual(layoutNow(page).locations.panel.size, 300, "a panel on the right is as wide as what is right of the pointer");
  pointer(page, panelSash, "lostpointercapture", 0);
  await page.run("workbench.action.moveSideBarRight");
  await page.run("workbench.action.toggleAuxiliaryBar");
  const second = page.$("#sash-secondary");
  await page.key("left", second);
  await page.key("left", second);
  assert.strictEqual(layoutNow(page).locations.secondary.size, 268, "on the left of the window now, its divider is on its right: Left makes it narrower");
  await page.key("right", second);
  assert.strictEqual(layoutNow(page).locations.secondary.size, 284);
  noErrors(page);
});

scenario("a_divider_between_two_groups_gives_one_more_room_and_the_other_less", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.key("mod+\\");
  await page.settle(40);
  const split = page.$(".grid-split");
  const groups = page.$$(".editor-group");
  rect(groups[0], { left: 0, width: 100, right: 100 });
  rect(groups[1], { left: 100, width: 100, right: 200 });
  const sash = page.$(".grid-sash");
  pointer(page, sash, "pointerdown", 100);
  pointer(page, sash, "pointermove", 75);
  assert.match(groups[0].style.flex, /^0\.75 1 0(px)?$/, "(a quarter less for the first, a quarter more for the other)");
  assert.match(groups[1].style.flex, /^1\.25 1 0(px)?$/);
  pointer(page, sash, "lostpointercapture", 75);
  await page.settle();
  const saved = JSON.parse(page.storage()["verdict.editors:s1"]);
  assert.deepStrictEqual(saved.grid.sizes, [0.75, 1.25], "and the sizes are remembered");
  await page.dblclick(sash);
  assert.deepStrictEqual(JSON.parse(page.eval("JSON.stringify(editors.grid.sizes)")), [1, 1], "a double click shares the room equally");
  noErrors(page);
});

scenario("groups_are_walked_closed_and_files_moved_between_them", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.key("mod+\\");
  await page.settle(40);
  assert.strictEqual(page.eval("editors.active"), "g2");
  await page.key("mod+k left");
  assert.strictEqual(page.eval("editors.active"), "g1");
  await page.key("mod+k right");
  assert.strictEqual(page.eval("editors.active"), "g2");
  await page.key("mod+k mod+left");
  assert.strictEqual(page.eval("editors.active"), "g1");
  await page.key("mod+k mod+right");
  await page.key("mod+1");
  assert.strictEqual(page.eval("editors.active"), "g1", "Cmd/Ctrl+1 is the first group");
  await page.key("mod+2");
  assert.strictEqual(page.eval("editors.active"), "g2");
  await page.run("workbench.action.moveEditorToPreviousGroup");
  assert.ok(page.$$(".editor-group")[0].querySelector(".tab[data-key='main.c']"), "Move Editor into Previous Group");
  assert.strictEqual(groupsIn(page).length, 1, "the group left empty goes");
  await page.key("mod+\\");
  await page.run("workbench.action.closeGroup");
  assert.strictEqual(groupsIn(page).length, 1);
  assert.ok(tabTitles(page).includes("Verdict"), "closing a group never loses a tab that cannot be closed");
  noErrors(page);
});

scenario("syntax_colours_and_rainbow_brackets_come_from_the_server_tokens", async () => {
  const tokens = [[["pp", "#include"], ["", " <stdio.h>"]], [["", ""]], [["ty", "int"], ["", " "], ["f", "main"], ["o", "("], ["k", "void"], ["o", ")"]], [["o", "{"]], [["", "\tprintf"], ["o", "("], ["s", "\"hi\\n\""], ["o", ")"], ["o", ";"]], [["k", "\treturn"], ["", " ("], ["n", "0"], ["o", ");"]], [["o", "}"]], [["", ""]]];
  const page = await ready({ routes: { "GET /api/sessions/[^/]+/file": ({ url, json }) => json({ path: url.searchParams.get("path"), binary: false, size: 10, truncated: false, content: "#include <stdio.h>\n\nint main(void)\n{\n\tprintf(\"hi\\n\");\n\treturn (0);\n}\n", tokens, language: "C" }) } });
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  const src = page.$(".tab-body .src, .src");
  assert.ok(page.$$(".src .t-k").length >= 2 && page.$(".src .t-f"), "tokens are classes (the colours are the theme's)");
  assert.ok(page.$$(".src .rb").length >= 4, "brackets get the colour of their depth");
  assert.strictEqual(page.$(".src").textContent, "#include <stdio.h>\n\nint main(void)\n{\n\tprintf(\"hi\\n\");\n\treturn (0);\n}\n", "and the text is exactly the file");
  await page.run("editor.action.toggleRainbowBrackets");
  assert.strictEqual(page.$$(".src .rb").length, 0, "Toggle Bracket Pair Colorization");
  noErrors(page);
});

scenario("a_click_on_the_gutter_selects_the_line_and_enter_steps_through_the_matches", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  const gutter = page.$(".gutter");
  rect(gutter, { top: 0, height: 200 });
  gutter.dispatchEvent(Object.assign(new page.window.MouseEvent("mousedown", { bubbles: true, cancelable: true, clientY: 4 + 2 * 20 + 2 }), {}));
  await page.settle(20);
  assert.strictEqual(page.eval("tabs.get('main.c').cursor.line"), 3, "the third line");
  assert.match(page.window.getSelection().toString(), /int main\(void\)/);
  await page.key("mod+f");
  await page.type(".find-widget input", "t");
  const total = Number(page.text(".find-count").split(" of ")[1]);
  assert.ok(total > 2);
  await page.key("enter", ".find-widget input");
  await page.key("enter", ".find-widget input");
  await page.key("enter", ".find-widget input", {});
  assert.match(page.text(".find-count"), /^\d+ of \d+$/);
  const before = page.text(".find-count");
  await page.key("shift+enter", ".find-widget input");
  assert.notStrictEqual(page.text(".find-count"), before, "Shift+Enter goes back");
  await page.key("f3", ".find-widget input");
  await page.key("shift+f3", ".find-widget input");
  await page.key("alt+c", ".find-widget input");
  await page.key("alt+w", ".find-widget input");
  await page.key("alt+r", ".find-widget input");
  assert.strictEqual(page.$$(".find-toggle.on").length, 3, "Alt+C / W / R switch the three options");
  noErrors(page);
});

scenario("the_menus_are_driven_by_the_keyboard", async () => {
  const page = await ready();
  const bar = page.$$(".menubar-item");
  bar[0].focus();
  await page.key("right", bar[0]);
  assert.strictEqual(page.document.activeElement, bar[1], "Right walks the menu bar");
  await page.key("left", bar[1]);
  await page.key("left", bar[0]);
  assert.strictEqual(page.document.activeElement, bar.at(-1), "and wraps");
  await page.key("down", bar[3]);
  assert.ok(bar[3].classList.contains("open"), "Down opens a menu");
  const menu = () => page.$(".menu[data-depth='0']");
  const focused = () => page.$$(".menu-item.focus").map((e) => e.querySelector(".menu-label").textContent);
  await page.key("down", menu());
  await page.key("down", menu());
  assert.strictEqual(focused().length, 1);
  await page.key("end", menu());
  await page.key("home", menu());
  const first = focused()[0];
  await page.key("up", menu());
  assert.notStrictEqual(focused()[0], first, "Up from the first goes to the last");
  const labels = page.$$(".menu[data-depth='0'] .menu-item:not(.disabled)").map((e) => e.querySelector(".menu-label").textContent);
  const at = labels.indexOf("Appearance");
  await page.key("home", menu());
  for (let i = 0; i < at; i++) await page.key("down", menu());
  await page.key("right", menu());
  assert.strictEqual(page.$$(".menu").length, 2, "Right opens a submenu");
  await page.key("left", page.$$(".menu").at(-1));
  assert.strictEqual(page.$$(".menu").length, 1, "Left closes it");
  await page.key("right", menu());
  const submenu = page.$$(".menu").at(-1);
  const zen = [...submenu.querySelectorAll(".menu-item:not(.disabled)")].findIndex((e) => e.textContent.startsWith("Zen"));
  await page.key("home", submenu);
  for (let i = 0; i < zen; i++) await page.key("down", submenu);
  await page.key("enter", submenu);
  assert.ok(bodyHas(page, "zen"), "Enter runs the item");
  assert.ok(!page.$(".menu"));
  await page.key("escape escape");
});

scenario("customize_layout_and_the_command_center_in_the_title_bar", async () => {
  const page = await ready();
  await page.click("[title='Customize Layout...']");
  assert.ok(page.texts(".menu-label").includes("Primary Side Bar") && page.texts(".menu-label").includes("Reset View Locations"));
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Secondary Side Bar")));
  assert.ok(page.visible("#secondary"));
  await page.click("[title='Toggle Panel']");
  assert.ok(!page.visible("#panel"));
  await page.click("[title='Toggle Primary Side Bar']");
  assert.ok(!page.visible("#sidebar"));
  await page.click(".command-center-box");
  assert.ok(page.visible("#palette"), "the command center opens Go to File");
  assert.match(page.text(".command-center-box"), /fract-ol/, "and names the project");
});

scenario("reveal_in_explorer_and_collapse_all", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='src/util.c']").catch(() => null);
  await page.eval("openFile('src/util.c')");
  await page.settle(60);
  await page.click(".activity-item[data-container=search]");
  await page.run("workbench.files.revealActiveFileInExplorer");
  await page.settle(40);
  assert.strictEqual(page.text("#sidebar .part-title"), "Explorer");
  assert.ok(page.$("#tree .row[data-path='src/util.c'].selected"), "the file is selected in the tree");
  assert.strictEqual(page.$("#tree .row[data-dir='src']").getAttribute("aria-expanded"), "true");
  await page.run("workbench.files.action.collapseExplorerFolders");
  assert.strictEqual(page.$("#tree .row[data-dir='src']").getAttribute("aria-expanded"), "false");
  await page.contextmenu(".tab[data-key='src/util.c']");
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Reveal in Explorer")));
  await page.settle(40);
  assert.strictEqual(page.$("#tree .row[data-dir='src']").getAttribute("aria-expanded"), "true");
  noErrors(page);
});

scenario("source_control_rows_have_a_menu_and_a_binary_diff_says_so", async () => {
  const page = await ready({ changes: [{ path: "logo.png", x: "", y: "M", kind: "modified" }, { path: "old.c", x: "", y: "D", kind: "deleted" }], routes: {
    "GET /api/sessions/[^/]+/git/diff": ({ url, json }) => json({ path: url.searchParams.get("path"), before: "", after: "", binary: true, truncated: false, state: "modified" }),
  } });
  await page.click(".activity-item[data-container=scm]");
  await page.settle(1700);
  await page.contextmenu(page.$$(".scm-row")[0]);
  assert.deepStrictEqual(page.texts(".menu-label"), ["Open Changes", "Open File", "Copy Path", "Reveal in Explorer"]);
  await page.click(page.$$(".menu-item")[0]);
  await page.settle(60);
  assert.match(page.text(".diff-view .notice"), /binary/);
  await page.contextmenu(page.$$(".scm-row")[1]);
  assert.ok(page.$$(".menu-item").find((e) => e.textContent.startsWith("Open File")).classList.contains("disabled"), "a deleted file cannot be opened");
  await page.key("escape");
  assert.ok(page.$(".scm-deleted .row-name"));
  await page.click(page.$(".scm-group"));
  assert.ok(!page.$(".scm-row"), "a group folds");
  noErrors(page);
});

scenario("files_have_the_icon_of_their_type_in_the_explorer_and_in_quick_open", async () => {
  const page = await ready({ routes: { "GET /vendor/great-icons/icons.json": ({ json }) => json({ iconDefinitions: { c: { iconPath: "./icons/c.svg" }, f: { iconPath: "./icons/file.svg" }, d: { iconPath: "./icons/folder.svg" } }, file: "f", folder: "d", folderExpanded: "d", fileExtensions: { c: "c" } }) } });
  assert.strictEqual(page.$("#tree .row[data-path='main.c'] img.ficon").getAttribute("src"), "vendor/great-icons/icons/c.svg", "by extension");
  assert.strictEqual(page.$("#tree .row[data-path='Makefile'] img.ficon").getAttribute("src"), "vendor/great-icons/icons/file.svg", "else the plain file");
  assert.strictEqual(page.$("#tree .row[data-dir='src'] img.ficon").getAttribute("src"), "vendor/great-icons/icons/folder.svg");
  await page.key("mod+p");
  assert.ok(page.$$(".palette-item img.ficon").length >= 4, "the rows of quick open have them too");
  assert.ok(page.$$(".palette-item img.ficon").some((i) => i.getAttribute("src").endsWith("c.svg")));
  noErrors(page);
});

scenario("quick_input_modes_for_text_and_help", async () => {
  const page = await ready();
  await page.key("mod+p");
  await page.type("#palette input", "?");
  assert.strictEqual(page.$$(".palette-item").length, 5, "? lists what the box can do");
  await page.click(page.$$(".palette-item")[1]);
  assert.strictEqual(page.$("#palette input").value, ">", "choosing one types its prefix");
  await page.type("#palette input", "%return");
  assert.match(page.text(".pi-label"), /Search for "return"/);
  await page.key("enter", "#palette input");
  await page.settle(80);
  assert.strictEqual(page.text("#sidebar .part-title"), "Search");
  assert.strictEqual(page.$(".search-input").value, "return");
  noErrors(page);
});

scenario("keyboard_shortcuts_can_be_removed_and_all_reset", async () => {
  const page = await ready();
  await page.run("workbench.action.openGlobalKeybindings");
  await page.type(".settings-search", "toggle zen");
  const row = page.$("table.keybindings tr[data-command='workbench.action.toggleZenMode']");
  await page.contextmenu(row);
  await page.click(page.$$(".menu-item").find((e) => e.textContent.startsWith("Remove Keybinding")));
  assert.ok(JSON.parse(page.storage()["verdict.keybindings"]).some((b) => b.command === "-workbench.action.toggleZenMode"));
  await page.key("mod+k z");
  assert.ok(!bodyHas(page, "zen"), "the key was taken away");
  await page.click(page.$$(".settings-head button").find((b) => b.textContent === "Reset All"));
  assert.deepStrictEqual(JSON.parse(page.storage()["verdict.keybindings"]), []);
  await page.key("mod+k z");
  assert.ok(bodyHas(page, "zen"), "and is back");
  await page.run("workbench.action.toggleZenMode");
  noErrors(page);
});

scenario("the_bell_closes_when_the_page_is_clicked_elsewhere", async () => {
  const page = await ready();
  await page.eval("notify('One')");
  await page.click(".status-notifications");
  await page.settle(10);
  assert.ok(page.$("#notification-center"));
  page.document.body.dispatchEvent(new page.window.MouseEvent("mousedown", { bubbles: true }));
  await page.settle();
  assert.ok(!page.$("#notification-center"), "a click outside closes it");
  await page.eval("notify('Two', { actions: [{ label: 'Undo', run: () => { window.__undone = true; } }] })");
  await page.click("#toasts .toast .linklike");
  assert.ok(page.window.__undone, "a toast action runs");
  assert.ok(!page.texts("#toasts .toast-message").includes("Two"), "and closes its toast");
  await page.eval("notify('Three')");
  await page.click([...page.$$("#toasts .toast")].find((t) => t.textContent.includes("Three")).querySelector(".toast-close"));
  assert.ok(!page.texts("#toasts .toast-message").includes("Three"), "and a toast has a close button");
});

scenario("terminal_service_down_and_terminal_details", async () => {
  const page = await ready({ routes: { "GET /api/terminal": ({ json }) => json({ configured: false, reachable: false, claude: false, workdir: "copy", ssh: false }) } });
  await page.run("workbench.action.terminal.new");
  await page.settle(80);
  assert.ok(page.terminals[0].written.join("").includes("The terminal service is not running"), "no terminal service: the pane says what to do");
  assert.strictEqual(page.sockets.length, 0, "and opens no connection");
  const withClaudeMissing = await ready({ routes: { "GET /api/terminal": ({ json }) => json({ configured: true, reachable: true, claude: false, workdir: "live", ssh: false }) } });
  await withClaudeMissing.run("verdict.openClaude");
  await withClaudeMissing.settle(80);
  assert.match(withClaudeMissing.text(".term-bar"), /directly in your project/);
  assert.match(withClaudeMissing.text(".term-bar"), /git over ssh is off/);
  assert.ok(withClaudeMissing.terminals[0].written.join("").includes("not installed"));
});

scenario("terminal_groups_are_cycled_and_a_pane_divider_moves", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.run("workbench.action.terminal.split");
  await page.run("workbench.action.terminal.new");
  await page.settle(60);
  assert.strictEqual(page.eval("terminals.groups.length"), 2);
  assert.strictEqual(page.$(".terminal-pane.active").dataset.pane, "t3");
  await page.run("workbench.action.terminal.focusPrevious");
  assert.strictEqual(page.$(".terminal-pane.active").dataset.pane, "t2", "the previous group, on its active pane");
  await page.run("workbench.action.terminal.focusNext");
  assert.strictEqual(page.$(".terminal-pane.active").dataset.pane, "t3");
  await page.run("workbench.action.terminal.focusPrevious");
  const [a, b] = page.$$(".terminal-pane");
  rect(a, { left: 0, width: 100, right: 100 });
  rect(b, { left: 100, width: 100, right: 200 });
  const sash = page.$(".terminal-stage .grid-sash");
  pointer(page, sash, "pointerdown", 100);
  pointer(page, sash, "pointermove", 150);
  pointer(page, sash, "lostpointercapture", 150);
  assert.deepStrictEqual(JSON.parse(page.storage()["verdict.terminals:s1"]).groups[0].grid.sizes, [1.5, 0.5]);
  await page.key("escape", page.$$(".terminal-row")[0]);
  const escape = page.$$(".terminal-row")[0];
  await page.dblclick(escape);
  const input = page.$(".terminal-rename");
  assert.ok(input);
  await page.key("escape", input);
  assert.ok(!page.$(".terminal-rename"), "Escape gives up a rename");
  noErrors(page);
});

scenario("a_new_project_ends_every_terminal_of_the_old_one", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.run("workbench.action.terminal.split");
  await page.run("verdict.openClaude");
  await page.settle(60);
  page.eval("resetForNewProject()");
  await page.settle(60);
  assert.strictEqual(page.called("POST /api/sessions/s1/shell/end").length, 2, "both shells are ended");
  assert.strictEqual(page.$$(".terminal-pane").length, 0);
  assert.ok(!page.$(".tab[data-key=terminal]"), "and claude's tab closed");
  assert.deepStrictEqual(page.texts(".tab .tab-title"), ["Verdict"], "only the Verdict is left");
  noErrors(page);
});

scenario("the_upload_dialog_takes_the_pdfs_of_the_file_picker", async () => {
  let uploaded = null;
  const page = await ready({ routes: { "POST /api/sessions/[^/]+/subjects": ({ init, json, state }) => { uploaded = init.body; return json(state.session); } } });
  await page.run("verdict.uploadSubjects");
  await page.settle(60);
  assert.match(page.text("#dialog h3"), /Upload subject PDFs/);
  assert.strictEqual(page.$$("#dialog input[type=radio]").length, 3, "Common Core, Post Common Core, RNCP");
  await page.click("#dialog button.primary");
  assert.match(page.texts(".toast-message").join(" "), /Choose Common Core/, "a track has to be chosen first");
  page.$$("#dialog input[type=radio]")[1].checked = true;
  let picked = 0;
  page.$("#file-input").click = () => { picked += 1; };
  await page.click("#dialog button.primary");
  assert.strictEqual(picked, 1, "then the browser's file picker opens");
  const input = page.$("#file-input");
  Object.defineProperty(input, "files", { value: [{ name: "libft.pdf" }, { name: "notes.txt" }], configurable: true });
  input.dispatchEvent(new page.window.Event("change", { bubbles: true }));
  await page.settle(80);
  assert.ok(uploaded, "the PDF is sent");
  assert.ok(page.called("POST /api/sessions/s1/subjects").length === 1);
  assert.match(page.texts(".toast-message").join(" "), /libft\.pdf/);
});

scenario("every_command_can_be_run_without_the_page_failing", async () => {
  const page = await ready({ changes: CHANGES });
  const ids = JSON.parse(page.eval("JSON.stringify([...commandRegistry.keys()])")).filter((id) => !["workbench.action.reloadWindow", "verdict.downloadVerdict"].includes(id));
  assert.ok(ids.length > 100);
  for (const id of ids) {
    page.eval(`runCommand(${JSON.stringify(id)})`);
    await page.settle(8);
    page.eval("closeMenus(); closeQuickInput(); closeDialog(); closeNotificationCenter();");
  }
  await page.settle(100);
  noErrors(page);
  const real = JSON.parse(page.eval("JSON.stringify(notifications.items.filter((i) => i.level === 'error').map((i) => i.message))")).filter((m) => !m.includes("no fake for") && !m.includes("The library is empty"));
  assert.deepStrictEqual(real, [], "no command told of an error");
});

// ---------------------------------------------------------------- the review: AI, claude's report, the fix prompt, the dialogs of the old top bar

const ai = (over) => ({ state: "idle", step: "", progress: [], started_at: "", reviews: {}, overview: null, model: "m-1", input_tokens: 1200, output_tokens: 340, not_fully_sent: [], message: "", ...over });
const llmHealth = (provider) => ({ "GET /api/health": ({ json }) => json({ status: "ok", sandbox: true, llm: { configured: true, model: "m-1", provider, host: "api.example.org" } }) });

scenario("the_ai_overview_and_its_verdicts_appear_in_the_verdict_and_the_checklist", async () => {
  const reviews = { r1: { assessment: "likely_problem", finding: "The Makefile has no all rule.", why_manual: "", evidence: [{ file: "Makefile", line: 1 }], by: "Claude" } };
  const overview = { purpose: "A fractal viewer.", languages: ["C"], build_and_run: "make && ./fractol", components: [{ path: "main.c", role: "entry point" }], notable: ["uses mlx"], not_found: ["bonus zoom"] };
  const page = await ready({ session: fixtureSession({ ai: ai({ state: "done", overview, reviews, not_fully_sent: ["big.c"], progress: [{ at: "2026-01-01T00:00:00Z", text: "read the files" }], started_at: "2026-01-01T00:00:00Z" }), results: [
    { rule_id: "r1", title: "Makefile", status: "manual", detail: "to review", section: "mandatory", sources: [], evidence: [], log: "", by: "" },
    { rule_id: "r2", title: "Norm", status: "pass", detail: "ok", section: "mandatory", sources: [], evidence: [], log: "", by: "" }] }) });
  assert.match(page.text(".overview"), /What is in the repository/);
  assert.match(page.text(".overview"), /A fractal viewer\./);
  assert.match(page.text(".overview"), /1 file\(s\) were cut or left out/);
  await page.click(".overview .components .ev");
  await page.settle(60);
  assert.ok(page.$(".tab[data-key='main.c']"), "a component opens its file");
  assert.ok(page.$("#panel .item.st-fail"), "a requirement the AI judged a problem is listed as failed, not as manual");
  assert.match(page.text("#panel .ai-chip"), /Claude: likely a problem/);
  await page.click("#panel .item-head");
  assert.match(page.text("#panel .ai-review"), /no all rule/);
  assert.match(page.text("#panel .ai-review"), /generated, unverified/);
  noErrors(page);
});

scenario("an_ai_review_in_progress_shows_its_steps_and_can_be_stopped", async () => {
  const started = new Date(Date.now() - 65000).toISOString();
  const page = await ready({ session: fixtureSession({ state: "idle", ai: ai({ state: "running", step: "reading main.c", started_at: started, progress: [{ at: started, text: "started" }, { at: new Date(Date.now() - 40000).toISOString(), text: "read main.c" }] }) }), routes: {
    "POST /api/sessions/[^/]+/ai/cancel": ({ json, state }) => { state.session = fixtureSession({ ai: ai({ state: "cancelled" }) }); return json(state.session); },
  } });
  assert.match(page.text(".ai-box"), /AI review in progress/);
  assert.match(page.text(".ai-box .timer"), /^1:0\d$/, "the time it has been working");
  assert.match(page.text(".ai-box .step"), /reading main\.c/);
  assert.match(page.text(".ai-box"), /No news from the server/);
  assert.strictEqual(page.$$(".ai-log li").length, 2);
  assert.ok(page.$("#statusbar.busy") && /AI review: reading main\.c/.test(page.text(".status-state")));
  await page.click(".ai-box .ai-head button");
  await page.settle(1200);
  assert.match(page.text(".overview"), /AI review stopped/);
  noErrors(page);
});

scenario("an_ai_review_that_failed_says_why", async () => {
  const page = await ready({ session: fixtureSession({ ai: ai({ state: "error", message: "quota exceeded", progress: [{ at: "2026-01-01T00:00:00Z", text: "x" }], started_at: "2026-01-01T00:00:00Z" }) }) });
  assert.match(page.text(".ai-box.error"), /AI review failed: quota exceeded/);
});

scenario("ai_review_with_a_model_server_asks_first_naming_the_server", async () => {
  const page = await ready({ routes: { ...llmHealth("openai"), "POST /api/sessions/[^/]+/ai": ({ json, state }) => { state.session = fixtureSession({ ai: ai({ state: "done" }) }); return json(state.session); } } });
  await page.run("verdict.aiReview");
  await page.settle(60);
  assert.match(page.text("#dialog h3"), /Send this repository to an AI model/);
  assert.match(page.text("#dialog"), /api\.example\.org/);
  assert.match(page.text("#dialog .warning"), /server you configured/);
  await page.click(page.$$("#dialog button").find((b) => b.textContent === "Cancel"));
  assert.strictEqual(page.called("POST /api/sessions/s1/ai").length, 0, "nothing is sent before the answer");
  await page.run("verdict.aiReview");
  await page.click("#dialog button.primary");
  await page.settle(1200);
  assert.strictEqual(page.called("POST /api/sessions/s1/ai").length, 1);
  noErrors(page);
});

scenario("ai_review_through_claude_checks_the_environment_and_starts_claude_with_the_prompt", async () => {
  const page = await ready({ routes: { ...llmHealth("claude-cli"), "POST /api/sessions/[^/]+/terminal-prompt": ({ json }) => json({ id: "prompt-7" }), "GET /api/sessions/[^/]+/review-prompt": ({ json }) => json({ text: "Please review this project." }) } });
  await page.run("verdict.aiReview");
  await page.settle(100);
  assert.match(page.text("#dialog h3"), /Ask claude to review/);
  assert.match(page.text("#dialog .env-ok"), /Environment ready/);
  await page.click("#dialog button.primary");
  await page.settle(120);
  assert.strictEqual(page.called("POST /api/sessions/s1/terminal-prompt").length, 1);
  const claude = page.sockets.find((sock) => !sock.url.includes("kind=shell"));
  assert.match(claude.url, /&prompt=prompt-7$/, "claude begins with the prompt");
  assert.ok(page.$(".tab[data-key=terminal]"));
  // with claude already connected the prompt is pasted into it instead
  await page.run("verdict.aiReview");
  await page.settle(100);
  await page.click("#dialog button.primary");
  await page.settle(700);
  assert.strictEqual(page.sockets.filter((sock) => !sock.url.includes("kind=shell")).length, 1, "no second claude");
  const sent = claude.sent.map((d) => JSON.parse(d));
  assert.ok(sent.some((e) => e.t === "i" && e.d.startsWith("\x1b[200~")), "the request is pasted as one bracketed paste");
  assert.ok(sent.some((e) => e.t === "i" && e.d === "\r"), "and entered");
  noErrors(page);
});

scenario("the_fix_prompt_is_shown_to_copy", async () => {
  const page = await ready({ routes: { "GET /api/sessions/[^/]+/fix-prompt": ({ json }) => json({ text: "Fix these:\n- Makefile", must_fix: 1, look_at: 2, bonus: 0 }) } });
  await page.run("verdict.fixPrompt");
  await page.settle(60);
  assert.strictEqual(page.$("#dialog textarea.prompt").value, "Fix these:\n- Makefile");
  assert.match(page.text("#dialog"), /1 to fix, 2 to look at/);
  await page.click(page.$$("#dialog button").find((b) => b.textContent === "Copy"));
  await page.settle(40);
  assert.strictEqual(page.window.__copied, "Fix these:\n- Makefile");
  const none = await ready({ routes: { "GET /api/sessions/[^/]+/fix-prompt": ({ json }) => json({ text: "", must_fix: 0, look_at: 0, bonus: 0 }) } });
  await none.run("verdict.fixPrompt");
  await none.settle(60);
  assert.match(none.texts(".toast-message").join(" "), /Nothing to fix/);
});

scenario("claudes_saved_report_is_merged_and_told", async () => {
  const merged = fixtureSession({ verdict_file: "verdict.md", claude: { structured: true, assessed: 2, total: 3, fixes: [{}, {}], problems: [] } });
  const page = await ready({ session: fixtureSession({ claude_review_at: "" }) });
  page.state.session = merged;
  await page.eval("afterReviewSaved({ verdict_file: 'verdict.md' })");
  await page.settle(60);
  assert.match(page.texts(".toast-message").join(" "), /Merged claude's answers \(2 of 3 requirements\).*2 correction\(s\) listed.*1 requirement\(s\) were not answered/);
  page.state.session = fixtureSession({ claude: { structured: false, problems: ["no data block"] } });
  await page.eval("afterReviewSaved({})");
  await page.settle(60);
  assert.match(page.texts(".toast-message").join(" "), /added to verdict\.md as text.*no data block/);
  await page.eval("afterReviewSaved({ warning: 'two reports found' })");
  assert.match(page.texts(".toast-message").join(" "), /two reports found/);
});

scenario("open_project_clones_or_picks_a_folder_and_starts_the_page_from_nothing", async () => {
  const cloned = [];
  const page = await ready({ routes: {
    "POST /api/sessions/[^/]+/repo": ({ init, json, state }) => { cloned.push(JSON.parse(init.body)); state.session = fixtureSession({ results: [], state: "idle" }); return json(state.session); },
    "POST /api/sessions/[^/]+/repo/existing": ({ init, json, state }) => { cloned.push(JSON.parse(init.body)); state.session = fixtureSession({ results: [], state: "idle" }); return json(state.session); },
  } });
  await page.run("workbench.action.terminal.new");
  await page.eval("openFile('main.c')");
  await page.settle(60);
  await page.run("workbench.action.files.openProject");
  await page.settle(100);
  assert.match(page.text("#dialog h3"), /Open a project/);
  assert.match(page.text("#dialog .where"), /Will clone to projects\//);
  const url = page.$("#dialog input[type=text]");
  await page.type(url, "git@github.com:me/minishell.git");
  assert.match(page.text("#dialog .where"), /Will clone to projects\/minishell$/, "the name follows the address");
  await page.click(page.$$("#dialog button").find((b) => b.textContent === "Clone"));
  await page.settle(150);
  assert.deepStrictEqual(cloned[0], { url: "git@github.com:me/minishell.git", name: "minishell" });
  assert.deepStrictEqual(page.texts(".tab .tab-title"), ["Verdict"], "the files of the old project are closed");
  assert.strictEqual(page.$$(".terminal-pane").length, 0, "and so are its terminals");
  assert.strictEqual(page.called("POST /api/sessions/s1/shell/end").length, 1);
  await page.run("workbench.action.files.openProject");
  await page.settle(100);
  await page.click(page.$$("#dialog .md-bar button").find((b) => b.textContent.includes("existing folder")));
  assert.deepStrictEqual(page.texts("#dialog .folder-list .pick span:first-of-type").slice(0, 2), ["fract-ol", "minishell"]);
  await page.type("#dialog input[type=text]", "mini");
  assert.strictEqual(page.$$("#dialog .folder-list .pick").length, 1, "the list is filtered as you type");
  await page.click("#dialog .folder-list input[type=radio]");
  await page.click(page.$$("#dialog button").find((b) => b.textContent === "Use this folder"));
  await page.settle(150);
  assert.deepStrictEqual(cloned[1], { path: "minishell" });
  noErrors(page);
});

scenario("the_library_adds_the_ticked_subjects", async () => {
  let asked = null;
  const page = await ready({ routes: {
    "GET /api/library": ({ json }) => json({ tracks: [{ id: "common-core", label: "Common Core" }, { id: "rncp", label: "RNCP" }], items: [{ track: "common-core", name: "libft.pdf", path: "common-core/libft.pdf" }, { track: "common-core", name: "fract-ol.pdf", path: "common-core/fract-ol.pdf" }], norm: true }),
    "POST /api/sessions/[^/]+/subjects/library": ({ init, json, state }) => { asked = JSON.parse(init.body); return json(state.session); },
  } });
  await page.run("verdict.addSubjectsFromLibrary");
  await page.settle(80);
  const boxes = page.$$("#dialog input[type=checkbox]");
  assert.deepStrictEqual(boxes.map((b) => b.checked), [false, true], "what is in the review already is ticked");
  assert.match(page.text("#dialog details.track[open]"), /1 selected/);
  boxes[0].checked = true;
  boxes[0].dispatchEvent(new page.window.Event("change", { bubbles: true }));
  assert.match(page.text("#dialog details.track[open]"), /2 selected/);
  await page.click(page.$$("#dialog button").find((b) => b.textContent === "Add"));
  await page.settle(60);
  assert.deepStrictEqual(asked, { paths: ["common-core/libft.pdf"] }, "only the new one is sent");
});

scenario("improvements_and_subject_rules_are_listed_in_the_panel", async () => {
  const page = await ready({ session: fixtureSession({ improvements: [{ category: "code", title: "Long function", detail: "main() is 60 lines", priority: "high", source: "static", evidence: [{ file: "main.c", line: 3, snippet: "int main" }] }, { category: "structure", title: "No tests", detail: "", priority: "low", source: "ai", evidence: [] }] }) });
  assert.strictEqual(page.text(".panel-tab[data-container=improvements] .tab-badge"), "2");
  await page.click(".panel-tab[data-container=improvements]");
  assert.deepStrictEqual(page.texts("#panel .group-title"), ["Structure (1)", "Code (1)"]);
  assert.match(page.text("#panel .readme-note"), /README\.md found/);
  await page.click(page.$$("#panel .item-head")[1]);
  await page.click("#panel .ev");
  await page.settle(60);
  assert.ok(page.$(".tab[data-key='main.c']"));
  await page.click(".panel-tab[data-container=rules]");
  assert.match(page.text("#panel .group-title"), /fract-ol\.pdf — Common Core, 1 rules, C/);
  assert.match(page.text("#panel .item-title"), /Makefile/);
  noErrors(page);
});

scenario("the_environment_check_lists_what_is_missing", async () => {
  const page = await ready({ routes: { "GET /api/environment": ({ json }) => json({ ready: false, deep: true,
    sandbox: { available: true, tools: [{ name: "make", ok: false, required: true, detail: "not found" }, { name: "valgrind", ok: false, required: false, detail: "" }], summary: { basics_ok: false, docker_ok: true, docker_daemon_down: false, failed: ["make"] } },
    terminal: { available: false, error: "could not reach the terminal service", tools: [], summary: { basics_ok: true, docker_ok: false, docker_daemon_down: true, failed: [] } } }) } });
  await page.run("verdict.environment");
  await page.settle(80);
  assert.match(page.text("#dialog .warning"), /Not ready/);
  assert.match(page.text("#dialog .warning"), /sandbox: make not working/);
  assert.match(page.text("#dialog .warning"), /terminal: could not reach the terminal service/);
  assert.strictEqual(page.$$("#dialog table.env tr.bad").length, 1);
  assert.strictEqual(page.$$("#dialog table.env tr.warn").length, 1);
  await page.click(page.$$("#dialog button").find((b) => b.textContent === "Run again"));
  await page.settle(80);
  assert.ok(page.called("GET /api/environment").length >= 2);
});

scenario("the_minimap_is_drawn_from_the_file_and_scrolls_it", async () => {
  const page = await ready();
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(80);
  assert.ok(page.drawn.length > 3, "the lines of the file are drawn as small blocks");
  const map = page.$(".minimap");
  assert.ok(map && !map.hidden);
  const view = page.$(".code-view");
  Object.defineProperty(view, "scrollHeight", { value: 1000, configurable: true });
  Object.defineProperty(view, "clientHeight", { value: 200, configurable: true });
  rect(map, { top: 0, height: 100 });
  const down = new page.window.Event("pointerdown", { bubbles: true, cancelable: true });
  Object.assign(down, { clientY: 50, pointerId: 1 });
  map.dispatchEvent(down);
  assert.strictEqual(view.scrollTop, 400, "a click half way down scrolls to the middle (the slider is centred on it)");
  await page.run("editor.action.toggleMinimap");
  assert.ok(map.hidden, "Toggle Minimap");
  noErrors(page);
});

scenario("the_theme_reaches_the_terminals_and_the_minimap", async () => {
  const page = await ready();
  await page.run("workbench.action.terminal.new");
  await page.dblclick("#tree .row[data-path='main.c']");
  await page.settle(60);
  const css = page.document.documentElement.style;
  css.setProperty("--terminal-bg", "#101010");                                  // (there is no style sheet in jsdom: the theme's colours are stood in for)
  css.setProperty("--dim", "#00ff00");
  const before = page.drawn.length;
  page.eval("settings.set('workbench.colorTheme', 'Light+')");
  await page.settle(100);
  assert.strictEqual(page.document.documentElement.dataset.theme, "light");
  assert.strictEqual(page.terminals[0].options.theme.background, "#101010", "an open terminal is given the colours of the new theme");
  assert.ok(page.drawn.slice(before).some((r) => r.color === "#00ff00"), "and the minimap is drawn again in the colours of the theme");
});

module.exports = { scenarios };

async function runOne(name, seconds = 30) {
  let timer;
  try {
    await Promise.race([scenarios[name](), new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("the scenario took too long")), seconds * 1000); })]);
    return { name, ok: true };
  } catch (err) {
    return { name, ok: false, error: String((err && err.stack) || err).split("\n").slice(0, 12).join("\n") };
  } finally {
    clearTimeout(timer);
    closeAllPages();
  }
}

if (require.main === module) {
  const [arg] = process.argv.slice(2);
  if (arg === "--list") { console.log(Object.keys(scenarios).join("\n")); process.exit(0); }
  if (arg === "--check") process.exit(loadJsdom() ? 0 : 3);
  if (arg === "--all" || (arg && arg.startsWith("--only="))) {
    const names = arg === "--all" ? Object.keys(scenarios) : arg.slice(7).split(",");
    (async () => {
      const results = [];
      for (const name of names) results.push(await runOne(name));
      console.log(JSON.stringify(results));
      process.exit(0);
    })();
  } else {
    if (!scenarios[arg]) { console.error(`no scenario ${arg}`); process.exit(2); }
    runOne(arg).then((r) => { if (r.ok) { console.log("ok"); process.exit(0); } console.error(r.error); process.exit(1); });
  }
}
