"use strict";

// The Settings editor and the Keyboard Shortcuts editor (both tabs of the editor area), the colour themes, and the About box.

// "editor.fontSize" is shown as "Editor: Font Size", as VS Code does.
function settingTitle(id) {
  const parts = id.split(".");
  const last = parts.pop();
  const words = (s) => s.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
  return `${words(parts[parts.length - 1] ?? "")}: ${words(last)}`;
}

function openSettings(group = null) {
  if (tabs.has("settings")) { showTab("settings"); return; }
  const search = h("input", { type: "text", class: "settings-search", placeholder: "Search settings", "aria-label": "Search settings", spellcheck: "false" });
  const body = h("div", { class: "settings-list" });
  const view = h("div", { class: "view settings-view" }, h("div", { class: "settings-head" }, h("h1", {}, "Settings"), search), body);
  const draw = () => {
    const needle = search.value.trim().toLowerCase();
    const shown = SETTINGS.filter((s) => !needle || `${settingTitle(s.id)} ${s.id} ${s.description} ${s.group}`.toLowerCase().includes(needle));
    const groups = [...new Set(shown.map((s) => s.group))];
    body.replaceChildren(...groups.flatMap((g) => [h("h2", {}, g), ...shown.filter((s) => s.group === g).map(settingRow)]));
    if (!shown.length) body.replaceChildren(h("p", { class: "hint" }, `No settings found for "${search.value}".`));
  };
  const settingRow = (s) => {
    const value = settings.get(s.id);
    const modified = value !== s.default;
    let control;
    if (s.type === "boolean") control = h("label", { class: "setting-check" }, h("input", { type: "checkbox", checked: value, onchange: (ev) => settings.set(s.id, ev.target.checked) }), s.description);
    else if (s.type === "enum") control = h("select", { onchange: (ev) => settings.set(s.id, ev.target.value) }, s.options.map((o) => h("option", { value: o, selected: o === value ? "" : null }, o)));
    else control = h("input", { type: s.type === "number" ? "number" : "text", value: String(value), min: s.min ?? null, max: s.max ?? null, onchange: (ev) => settings.set(s.id, s.type === "number" ? Number(ev.target.value) : ev.target.value) });
    return h("div", { class: `setting ${modified ? "modified" : ""}`, "data-setting": s.id },
      h("div", { class: "setting-title" }, settingTitle(s.id), modified ? h("span", { class: "setting-modified" }, "(Modified)") : null,
        modified ? h("button", { class: "linklike", onclick: () => settings.reset(s.id) }, "Reset Setting") : null),
      s.type === "boolean" ? null : h("div", { class: "setting-description" }, s.description), control);
  };
  search.addEventListener("input", draw);
  // A setting changed (here or elsewhere): its row is built again, with the mark and the Reset link, and keeps the focus it had.
  bus.on("setting", (id) => {
    if (!tabs.has("settings")) return;
    const row = $(`.setting[data-setting="${CSS.escape(id)}"]`, view);
    const item = SETTINGS.find((x) => x.id === id);
    if (!row || !item) { draw(); return; }
    const hadFocus = row.contains(document.activeElement);
    const fresh = settingRow(item);
    row.replaceWith(fresh);
    if (hadFocus) fresh.querySelector("input, select")?.focus();
  });
  draw();
  addTab("settings", "Settings", view, true, { group: group && editors.groups[group] ? group : editors.active });
  Object.assign(tabs.get("settings"), { kind: "settings", iconEl: () => icon("gear", 14) });
  showTab("settings");
  search.focus();
}

// ------------------------------------------------------------------ keyboard shortcuts

// Asks for a key or a chord: shows what is typed, Enter accepts it, Escape gives up.
function recordKeys() {
  return new Promise((resolve) => {
    const typed = [];
    const shown = h("div", { class: "record-keys-typed" }, "…");
    const box = h("div", { class: "record-keys" }, h("p", {}, "Press desired key combination and then press ENTER."), shown);
    dialog("Keybinding", box, [h("button", { onclick: () => finish(null) }, "Cancel")]);
    const finish = (value) => { document.removeEventListener("keydown", onKey, true); closeDialog(); resolve(value); };
    const onKey = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (ev.key === "Escape") return finish(null);
      if (ev.key === "Enter" && typed.length && !ev.metaKey && !ev.ctrlKey) return finish(typed.join(" "));
      const stroke = strokeFromEvent(ev, IS_MAC);
      if (!stroke) return;
      if (typed.length >= 2) typed.length = 0;
      typed.push(stroke);
      shown.textContent = typed.map((s) => showKey(s, IS_MAC)).join(" ");
    };
    document.addEventListener("keydown", onKey, true);
  });
}

function openKeybindings(group = null) {
  if (tabs.has("keybindings")) { showTab("keybindings"); return; }
  const search = h("input", { type: "text", class: "settings-search", placeholder: "Type to search in keybindings", "aria-label": "Search keybindings", spellcheck: "false" });
  const table = h("table", { class: "keybindings" });
  const view = h("div", { class: "view settings-view" }, h("div", { class: "settings-head" }, h("h1", {}, "Keyboard Shortcuts"), search,
    h("button", { onclick: () => { setUserKeybindings([]); draw(); notify("All keyboard shortcuts are back to their defaults."); } }, "Reset All")), table);
  const draw = () => {
    const needle = search.value.trim().toLowerCase();
    const rows = [];
    for (const spec of commandRegistry.values()) {
      if (spec.hidden) continue;
      const mine = bindingsOf(spec.id);
      const entries = mine.length ? mine : [null];
      for (const b of entries) rows.push({ spec, b });
    }
    const text = ({ spec, b }) => `${commandTitle(spec)} ${spec.id} ${b ? b.strokes.map((s) => showKey(s, IS_MAC)).join(" ") + " " + b.strokes.join(" ") : ""}`.toLowerCase();
    const shown = rows.filter((r) => !needle || text(r).includes(needle)).sort((a, b) => commandTitle(a.spec).localeCompare(commandTitle(b.spec)));
    table.replaceChildren(
      h("thead", {}, h("tr", {}, ["Command", "Keybinding", "When", "Source"].map((t) => h("th", {}, t)))),
      h("tbody", {}, shown.map(({ spec, b }) => h("tr", {
        class: b?.source === "user" ? "user" : "", "data-command": spec.id,
        ondblclick: () => editBinding(spec, b),
        oncontextmenu: (ev) => showContextMenu(ev, [
          { label: "Change Keybinding...", run: () => editBinding(spec, b) },
          { label: "Add Keybinding...", run: () => editBinding(spec, null) },
          { label: "Remove Keybinding", disabled: !b, run: () => removeBinding(spec, b) },
          "-",
          { label: "Copy Command ID", run: () => copyText(spec.id, "the command id") },
        ]),
      },
      h("td", { class: "cmd-title" }, commandTitle(spec), h("div", { class: "cmd-id" }, spec.id)),
      h("td", { class: "cmd-key" }, b ? b.strokes.map((s) => h("kbd", {}, showKey(s, IS_MAC))) : h("button", { class: "linklike", onclick: () => editBinding(spec, null) }, "Add keybinding"),
        h("button", { class: "icon-button edit-binding", title: "Change Keybinding", onclick: () => editBinding(spec, b) }, icon("edit", 14))),
      h("td", { class: "cmd-when" }, b?.when ?? ""),
      h("td", { class: "cmd-source" }, b ? (b.source === "user" ? "User" : "Default") : "")))));
  };
  async function editBinding(spec, previous) {
    const key = await recordKeys();
    if (!key) return;
    const user = store.get(USER_KEYBINDINGS, []).filter((o) => !(o.command === spec.id && previous && o.key === previous.strokes.join(" ")));
    if (previous && previous.source === "default") user.push({ command: `-${spec.id}`, key: previous.strokes.join(" ") });
    user.push({ command: spec.id, key, ...(spec.when ? { when: spec.when } : {}) });
    setUserKeybindings(user);
    const others = bindings.filter((x) => x.command !== spec.id && x.strokes.join(" ") === normalizeChord(key).join(" ")).map((x) => commandTitle(commandRegistry.get(x.command) ?? { title: x.command }));
    if (others.length) notify(`${key} is also used by: ${others.join(", ")}.`, { level: "warning" });
    draw();
  }
  function removeBinding(spec, b) {
    const user = store.get(USER_KEYBINDINGS, []).filter((o) => !(o.command === spec.id && o.key === b.strokes.join(" ")));
    if (b.source === "default") user.push({ command: `-${spec.id}`, key: b.strokes.join(" ") });
    setUserKeybindings(user);
    draw();
  }
  search.addEventListener("input", draw);
  bus.on("bindings", () => { if (tabs.has("keybindings")) draw(); });
  draw();
  addTab("keybindings", "Keyboard Shortcuts", view, true, { group: group && editors.groups[group] ? group : editors.active });
  Object.assign(tabs.get("keybindings"), { kind: "keybindings", iconEl: () => icon("command", 14) });
  showTab("keybindings");
  search.focus();
}

// ------------------------------------------------------------------ colour themes

function applyTheme() {
  document.documentElement.dataset.theme = THEME_IDS[settings.get("workbench.colorTheme")] ?? "modern";
  bus.emit("theme");
  bus.emit("fit");
}

async function pickTheme() {
  const before = settings.get("workbench.colorTheme");
  const chosen = await quickPick({
    title: "Select Color Theme", placeholder: "Select Color Theme (Up/Down Keys to Preview)",
    items: THEMES.map((t) => ({ label: t, picked: t === before, detail: t === before ? "current" : "" })),
    onHighlight: (item) => { if (item) document.documentElement.dataset.theme = THEME_IDS[item.label] ?? "modern"; },
    onCancel: () => applyTheme(),
  });
  if (chosen) settings.set("workbench.colorTheme", chosen.label);
  applyTheme();
}

// ------------------------------------------------------------------ about

function showAbout() {
  dialog("About", h("div", {},
    h("p", {}, h("strong", {}, "verdict"), " reviews a 42 project against its subject: scripts check what they can, claude and the AI weigh the rest."),
    h("table", { class: "about" }, h("tbody", {},
      [["Session", sid], ["Project", session?.repo?.path ?? "none"], ["Commit", session?.repo?.commit ?? "none"], ["Browser", navigator.userAgent], ["Layout", `${layout.locations.sidebar.order.length} side bar views, ${layout.locations.panel.order.length} panel views`]]
        .map(([k, v]) => h("tr", {}, h("td", {}, k), h("td", { class: "mono" }, String(v)))))),
    h("p", { class: "hint" }, "The interface follows VS Code: the same layout, menus, shortcuts and settings where a web page can have them. Browsers keep Cmd/Ctrl+W, T, N and Ctrl+Tab for themselves.")),
  [h("button", { class: "primary", onclick: closeDialog }, "OK")]);
}
