"use strict";

// Commands: every action of the page has an id, a title and (maybe) a key. The menus, the command palette and the keyboard all run the
// same commands. A key can be a chord (Cmd+K then Z) and can depend on where the focus is (a "when" clause), as in VS Code.

const commandRegistry = new Map();

// spec: { id, title, category?, run(...args), keys?: "mod+p" | ["mod+p", ...], when?, inTerminal?, enabled?(), hidden?, checked?() }
function registerCommand(spec) {
  commandRegistry.set(spec.id, spec);
}

async function runCommand(id, ...args) {
  const spec = commandRegistry.get(id);
  if (!spec) { notify(`The command '${id}' does not exist.`, { level: "error" }); return undefined; }
  if (spec.enabled && !spec.enabled()) {
    if (spec.unavailable) notify(spec.unavailable(), { level: "info" });                  // (a menu greys the command out; the keyboard says why nothing happened)
    return undefined;
  }
  try { return await spec.run(...args); } catch (err) { notify(err.message, { level: "error" }); return undefined; }
}

const commandEnabled = (id) => { const spec = commandRegistry.get(id); return !!spec && (!spec.enabled || !!spec.enabled()); };
const commandTitle = (spec) => (spec.category ? `${spec.category}: ${spec.title}` : spec.title);

// ------------------------------------------------------------------ where the focus is (what "when" clauses ask about)

const context = {
  isMac: IS_MAC, hasRepo: false, editorFocus: false, terminalFocus: false, inputFocus: false, sideBarFocus: false, panelFocus: false,
  explorerFocus: false, searchFocus: false, findWidgetVisible: false, findInputFocus: false, quickInputVisible: false, dialogVisible: false, menuOpen: false,
  fileEditor: false, diffEditor: false, terminalIsOpen: false, multipleEditorGroups: false,
};

function setContext(key, value) {
  if (context[key] === value) return;
  context[key] = value;
  bus.emit("context", key, value);
}

function contextFromFocus(target) {
  const el = target && target.closest ? target : null;
  setContext("inputFocus", !!el && !!el.closest("input, textarea, select, [contenteditable='true']") && !el.closest(".xterm"));
  setContext("terminalFocus", !!el && !!el.closest(".xterm, .terminal-pane"));
  setContext("editorFocus", !!el && !!el.closest("#editor-area") && !el.closest(".xterm"));
  setContext("sideBarFocus", !!el && !!el.closest("#sidebar, #secondary"));
  setContext("panelFocus", !!el && !!el.closest("#panel"));
  setContext("explorerFocus", !!el && !!el.closest("#tree"));
  setContext("searchFocus", !!el && !!el.closest(".search-view"));
  setContext("findInputFocus", !!el && !!el.closest(".find-widget input"));
}

// ------------------------------------------------------------------ keys

const USER_KEYBINDINGS = "verdict.keybindings";
let bindings = [];

function defaultBindings() {
  const out = [];
  for (const spec of commandRegistry.values()) {
    for (const key of [].concat(spec.keys ?? [])) out.push({ command: spec.id, key, when: spec.when ?? "" });
  }
  return out;
}

function loadBindings() {
  bindings = resolveBindings(defaultBindings(), store.get(USER_KEYBINDINGS, []));
  bus.emit("bindings");
}

function bindingsOf(commandId) {
  return bindings.filter((b) => b.command === commandId);
}

// How the first key of a command is written for a menu or the palette: "⇧⌘P", "Ctrl+Shift+P", "⌘K ⌘S".
function keyLabel(commandId) {
  const b = bindingsOf(commandId)[0];
  return b ? b.strokes.map((s) => showKey(s, IS_MAC)).join(" ") : "";
}

function setUserKeybindings(list) {
  store.set(USER_KEYBINDINGS, list);
  loadBindings();
}

// On Windows and Linux Ctrl is the shell's inside a terminal (Ctrl+B, Ctrl+P, ...): only the commands that say so take it there.
function appliesHere(binding) {
  if (!context.terminalFocus || IS_MAC) return true;
  const first = binding.strokes[0];
  return !/(^|\+)(mod|ctrl)(\+|$)/.test(first) || commandRegistry.get(binding.command)?.inTerminal === true;
}

let chord = { typed: [], exact: null, timer: null };

function clearChord() {
  clearTimeout(chord.timer);
  chord = { typed: [], exact: null, timer: null };
  bus.emit("chord", null);
}

document.addEventListener("keydown", (ev) => {
  if (ev.isComposing) return;
  const stroke = strokeFromEvent(ev, IS_MAC);
  if (!stroke) return;
  contextFromFocus(ev.target);
  if (context.dialogVisible && !chord.typed.length) return;
  // a key that types or moves in a field is text, not a command (F1, F3, Escape... and anything with Cmd, Ctrl or Alt are still commands)
  if (context.inputFocus && !chord.typed.length && !/(^|\+)(mod|ctrl|alt|meta)(\+|$)/.test(stroke) && /^(shift\+)?(.|space|enter|backspace|delete|left|right|up|down|home|end|pageup|pagedown|tab)$/.test(stroke)) return;
  const typed = [...chord.typed, stroke];
  const { exact, more } = matchChord(bindings.filter(appliesHere), typed, context);
  if (more) {
    ev.preventDefault();
    ev.stopPropagation();
    clearTimeout(chord.timer);
    chord = { typed, exact, timer: setTimeout(() => { const run = chord.exact; clearChord(); if (run) runCommand(run.command); }, 1800) };
    bus.emit("chord", typed);
    return;
  }
  if (exact) {
    ev.preventDefault();
    ev.stopPropagation();
    clearChord();
    runCommand(exact.command);
    return;
  }
  if (chord.typed.length) {                                    // a chord that leads nowhere swallows its last key, as VS Code does
    ev.preventDefault();
    ev.stopPropagation();
    if (stroke !== "escape") notify(`The key combination (${typed.map((s) => showKey(s, IS_MAC)).join(", ")}) is not a command.`, { level: "warning" });
    clearChord();
  }
}, true);

document.addEventListener("focusin", (ev) => contextFromFocus(ev.target), true);
