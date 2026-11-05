// The real page (index.html and every script, in the order the page loads them) booted in jsdom, with a fake server behind fetch, a fake xterm
// and a fake WebSocket. For tests/test_ui.py. There is no layout engine here (every box is 0 x 0): what is checked is what the page builds,
// what it stores and what it asks the server for, not how it looks.
//
// jsdom is looked for in $JSDOM_PATH, then next to this file (npm install in tests/js), then wherever node finds it.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const STATIC = path.join(__dirname, "../../src/verdict/static");

function loadJsdom() {
  const wanted = [process.env.JSDOM_PATH, path.join(__dirname, "node_modules/jsdom"), "jsdom"].filter(Boolean);
  for (const candidate of wanted) {
    try { return require(candidate); } catch { /* try the next one */ }
  }
  return null;
}

const none = { fail: 0, warn: 0, manual: 0, skipped: 0, na: 0, pass: 0 };

function fixtureSession(over = {}) {
  return {
    id: "s1", state: "done", message: "",
    repo: { url: "git@github.com:u/fract-ol.git", path: "fract-ol", name: "fract-ol", commit: "abc1234", subject: "last commit", author: "me" },
    subjects: [{ name: "fract-ol.pdf", kind: "subject", track: "common-core", lang: "c", pages: 3, rules: [{ rule_id: "r1", title: "Makefile", kind: "auto", unit: ".", section: "mandatory", text: "a Makefile" }] }],
    results: [
      { rule_id: "r1", title: "Makefile", status: "fail", detail: "no all rule", section: "mandatory", sources: [{ pdf: "fract-ol.pdf", page: 2 }], evidence: [{ file: "Makefile", line: 1, snippet: "all:" }], log: "", by: "" },
      { rule_id: "r2", title: "Norm", status: "pass", detail: "ok", section: "mandatory", sources: [], evidence: [], log: "", by: "" },
    ],
    improvements: [], claude: { structured: false }, readme: { present: true, name: "README.md", lines: 10 }, verdict_file: "verdict.md", claude_review_at: "",
    ai: { state: "idle", step: "", progress: [], started_at: "", reviews: {}, overview: null, model: "", input_tokens: 0, output_tokens: 0, not_fully_sent: [], message: "" },
    summary: { overall: "FAIL", mandatory: { ...none, fail: 1, pass: 1 }, bonus: { ...none }, reason: "", decided_by: "", lists: "FAIL" },
    ...over,
  };
}

const FILES = {
  "Makefile": "all:\n\t@echo ok\n",
  "main.c": "#include <stdio.h>\n\nint main(void)\n{\n\tprintf(\"hi\\n\");\n\treturn (0);\n}\n",
  "src/util.c": "int util(int a)\n{\n\treturn (a + 1);\n}\n",
  "README.md": "# fract-ol\n\nA fractal explorer.\n",
};
const LANGUAGES = { c: "C", md: "Markdown", Makefile: "Makefile" };
const TREE = [{ path: "src", type: "dir" }, { path: "Makefile", type: "file" }, { path: "main.c", type: "file" }, { path: "src/util.c", type: "file" }, { path: "README.md", type: "file" }];

class FakeTerminal {
  constructor(options) { this.options = options || {}; this.cols = 80; this.rows = 24; this.written = []; this.dataHandlers = []; this.resizeHandlers = []; }
  loadAddon(addon) { addon.term = this; }
  open(el) {
    this.el = el;
    const box = el.ownerDocument.createElement("div");
    box.className = "xterm";
    this.input = el.ownerDocument.createElement("textarea");          // (xterm.js reads the keys in a textarea of its own)
    this.input.className = "xterm-helper-textarea";
    box.append(this.input);
    el.append(box);
  }
  onData(f) { this.dataHandlers.push(f); }
  onResize(f) { this.resizeHandlers.push(f); }
  onSelectionChange() {}
  write(d) { this.written.push(d); }
  writeln(d) { this.written.push(`${d}\n`); }
  clear() { this.cleared = true; }
  reset() {}
  focus() { this.focused = true; }
  dispose() { this.disposed = true; }
  hasSelection() { return false; }
  getSelection() { return ""; }
}
class FakeFit { fit() {} }

const KEYS = { enter: ["Enter", "Enter"], escape: ["Escape", "Escape"], tab: ["Tab", "Tab"], space: [" ", "Space"], left: ["ArrowLeft", "ArrowLeft"], right: ["ArrowRight", "ArrowRight"], up: ["ArrowUp", "ArrowUp"], down: ["ArrowDown", "ArrowDown"],
  pagedown: ["PageDown", "PageDown"], pageup: ["PageUp", "PageUp"], home: ["Home", "Home"], end: ["End", "End"], delete: ["Delete", "Delete"], backspace: ["Backspace", "Backspace"],
  "`": ["`", "Backquote"], "-": ["-", "Minus"], "=": ["=", "Equal"], "[": ["[", "BracketLeft"], "]": ["]", "BracketRight"], "\\": ["\\", "Backslash"], ";": [";", "Semicolon"], "'": ["'", "Quote"], ",": [",", "Comma"], ".": [".", "Period"], "/": ["/", "Slash"] };

function keyInit(binding, mac) {
  const parts = binding.split("+");
  const name = parts.pop();
  const init = { bubbles: true, cancelable: true, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false };
  for (const part of parts) {
    if (part === "mod") init[mac ? "metaKey" : "ctrlKey"] = true;
    else if (part === "ctrl") init.ctrlKey = true;
    else if (part === "meta") init.metaKey = true;
    else if (part === "alt") init.altKey = true;
    else if (part === "shift") init.shiftKey = true;
  }
  if (KEYS[name]) [init.key, init.code] = KEYS[name];
  else if (/^f\d{1,2}$/.test(name)) { init.key = name.toUpperCase(); init.code = name.toUpperCase(); }
  else if (/^[a-z]$/.test(name)) { init.key = name; init.code = `Key${name.toUpperCase()}`; }
  else if (/^\d$/.test(name)) { init.key = name; init.code = `Digit${name}`; }
  else { init.key = name; init.code = name; }
  return init;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const openPages = [];
function closeAllPages() {
  while (openPages.length) { try { openPages.pop().window.close(); } catch { /* already closed */ } }        // (a page has timers of its own: they stop with it)
}

// options: session, changes (git status files), routes ({ "METHOD /path": handler }), storage ({ key: value }), platform ("MacIntel" for a Mac), url
async function openPage(options = {}) {
  const jsdom = loadJsdom();
  if (!jsdom) throw new Error("jsdom is not installed (npm install in tests/js, or set JSDOM_PATH)");
  const { JSDOM, VirtualConsole } = jsdom;
  const calls = [];
  const errors = [];
  const sockets = [];
  const terminals = [];
  const virtual = new VirtualConsole();
  virtual.on("jsdomError", (e) => { if (!/Not implemented/.test(String(e.message))) errors.push(`jsdomError: ${e.message}`); });
  virtual.on("error", (...a) => errors.push(`console.error: ${a.map(String).join(" ")}`));
  virtual.on("warn", (...a) => errors.push(`console.warn: ${a.map(String).join(" ")}`));
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  const dom = new JSDOM(html, { url: options.url || "http://localhost:8000/", runScripts: "outside-only", pretendToBeVisual: true, virtualConsole: virtual });
  const w = dom.window;
  const mac = /Mac/.test(options.platform || "");
  for (const [k, v] of Object.entries(options.storage || {})) w.localStorage.setItem(k, v);

  const state = { diffs: options.diffs || {}, session: options.session || fixtureSession(), changes: options.changes || [], shells: options.shells || { panes: [], claude: false }, terminal: { configured: true, reachable: true, claude: true, workdir: "copy", ssh: true } };
  const json = (data, ok = true, code = 200) => ({ ok, status: code, statusText: ok ? "OK" : "Error", json: async () => data, text: async () => (typeof data === "string" ? data : JSON.stringify(data)) });
  const defaults = {
    "GET /api/health": () => json({ status: "ok", sandbox: true, llm: { configured: false, model: "", provider: "", host: "" } }),
    "GET /api/sessions/[^/]+": () => json(state.session),
    "POST /api/sessions": () => json(state.session),
    "GET /api/ssh": () => json({ ok: true, keys: ["k"], message: "ok" }),
    "GET /api/terminal": () => json(state.terminal),
    "GET /api/sessions/[^/]+/tree": () => json(TREE),
    "GET /api/sessions/[^/]+/file": ({ url }) => { const p = url.searchParams.get("path"); return p in FILES ? json({ path: p, binary: false, size: FILES[p].length, truncated: false, content: FILES[p], tokens: null, language: LANGUAGES[p.split("/").pop().replace(/^.*\./, "")] ?? LANGUAGES[p] ?? null }) : json({ detail: "not a file" }, false, 400); },
    "GET /api/sessions/[^/]+/shells": () => json(state.shells),
    "POST /api/sessions/[^/]+/shell/end": () => json({ ok: true }),
    "POST /api/sessions/[^/]+/terminal/end": () => json({ ok: true }),
    "GET /api/sessions/[^/]+/git/status": () => json({ available: true, error: "", branch: "main", head: "abc1234", upstream: "origin/main", ahead: 1, behind: 0, files: state.changes, truncated: false }),
    "GET /api/sessions/[^/]+/verdict.md": () => json("# Verdict\n\nFAIL\n"),
    "GET /vendor/great-icons/icons.json": () => json({ iconDefinitions: {}, file: "f", folder: "d", folderExpanded: "d" }),
    "GET /api/sessions/[^/]+/search": () => json({ error: "", total: 1, truncated: false, files: [{ path: "main.c", matches: [{ line: 6, col: 1, length: 6, preview: "\treturn (0);", preview_start: 0 }] }] }),
    "GET /api/projects": () => json({ root: "projects" }),
    "GET /api/projects/existing": () => json({ folders: [{ path: "fract-ol", git: true }, { path: "minishell", git: true }] }),
    "GET /api/environment": () => json({ ready: true, deep: true, sandbox: { available: true, tools: [{ name: "make", ok: true, required: true, detail: "GNU Make" }], summary: { basics_ok: true, docker_ok: true, docker_daemon_down: false, failed: [] } }, terminal: { available: true, tools: [], summary: { basics_ok: true, docker_ok: true, docker_daemon_down: false, failed: [] } } }),
    "GET /api/sessions/[^/]+/git/diff": ({ url }) => {
      const p = url.searchParams.get("path");
      const after = state.diffs?.[p] ?? FILES[p] ?? "";
      return json({ path: p, before: FILES[p] ?? "", after, binary: false, truncated: false, state: p in FILES ? "modified" : "added" });
    },
    "GET /api/library": () => json({ tracks: [{ id: "common-core", label: "Common Core" }, { id: "post-common-core", label: "Post Common Core" }, { id: "rncp", label: "RNCP" }], items: [], norm: true }),
  };
  const routes = { ...defaults, ...(options.routes || {}) };
  w.fetch = async (url, init = {}) => {
    const u = new URL(url, "http://localhost:8000/");
    const route = `${init.method || "GET"} ${u.pathname}`;
    calls.push({ route, search: u.search, body: init.body });
    for (const [pattern, handler] of Object.entries(routes)) {
      if (!new RegExp(`^${pattern.replace(/\{[^}]+\}/g, "[^/]+")}$`).test(route)) continue;
      const answer = await handler({ url: u, init, json, state });
      if (answer !== undefined) return answer;
    }
    return json({ detail: `no fake for ${route}` }, false, 404);
  };
  w.WebSocket = class {
    constructor(url) { this.url = url; this.readyState = 0; this.sent = []; sockets.push(this); setTimeout(() => { this.readyState = 1; this.onopen?.({}); }, 0); }
    send(data) { this.sent.push(data); }
    close() { this.readyState = 3; }
  };
  w.WebSocket.OPEN = 1;
  w.ResizeObserver = class { observe() {} disconnect() {} unobserve() {} };
  w.Terminal = class extends FakeTerminal { constructor(o) { super(o); terminals.push(this); } };
  w.FitAddon = { FitAddon: FakeFit };
  w.CSS = { escape: (s) => String(s).replace(/[^a-zA-Z0-9_-]/g, (c) => `\\${c}`) };
  w.Element.prototype.scrollIntoView = function () {};
  w.HTMLElement.prototype.setPointerCapture = function () {};
  w.document.execCommand = () => true;
  const drawn = [];                                                              // (a canvas that remembers what was drawn on it)
  w.HTMLCanvasElement.prototype.getContext = function () {
    const ctx = { fillStyleSeen: "", scale() {}, clearRect() {}, fillRect: (x, y, width, height) => drawn.push({ x, y, width, height, color: ctx.fillStyleSeen }) };
    Object.defineProperty(ctx, "fillStyle", { get: () => ctx.fillStyleSeen, set: (v) => { ctx.fillStyleSeen = v; } });
    return ctx;
  };
  w.requestAnimationFrame = (f) => setTimeout(() => f(Date.now()), 0);
  Object.defineProperty(w.navigator, "clipboard", { value: { writeText: async (t) => { w.__copied = t; } }, configurable: true });
  Object.defineProperty(w.navigator, "platform", { value: options.platform || "Linux x86_64", configurable: true });
  w.addEventListener("error", (e) => errors.push(`uncaught: ${e.message}`));
  w.addEventListener("unhandledrejection", (e) => errors.push(`unhandledrejection: ${e.reason && e.reason.message}`));

  const context = dom.getInternalVMContext();
  for (const src of [...html.matchAll(/<script src="([^"]+)"/g)].map((m) => m[1])) {
    if (src.startsWith("vendor/")) continue;                                    // (xterm needs a real canvas: the page gets the fake above)
    try { new vm.Script(fs.readFileSync(path.join(STATIC, src), "utf8"), { filename: src }).runInContext(context); } catch (err) { errors.push(`load ${src}: ${err.stack.split("\n").slice(0, 4).join(" | ")}`); }
  }
  const d = w.document;

  const page = {
    window: w, document: d, calls, errors, sockets, terminals, drawn, state, mac, json,
    $: (sel, root = d) => root.querySelector(sel),
    $$: (sel, root = d) => [...root.querySelectorAll(sel)],
    text: (sel, root = d) => (root.querySelector(sel)?.textContent ?? null),
    texts: (sel, root = d) => [...root.querySelectorAll(sel)].map((e) => e.textContent),
    eval: (code) => w.eval(code),
    sleep,
    async settle(ms = 40) { await sleep(ms); },
    storage: () => Object.fromEntries(Array.from({ length: w.localStorage.length }, (_, i) => [w.localStorage.key(i), w.localStorage.getItem(w.localStorage.key(i))])),
    called: (route) => calls.filter((c) => c.route === route || c.route.startsWith(`${route}`)),
    el(target) { return typeof target === "string" ? d.querySelector(target) : target; },
    async click(target, init = {}) {
      const el = page.el(target);
      if (!el) throw new Error(`nothing to click: ${target}`);
      for (const type of ["mousedown", "mouseup", "click"]) el.dispatchEvent(new w.MouseEvent(type, { bubbles: true, cancelable: true, ...init }));
      await page.settle();
    },
    async dblclick(target) { const el = page.el(target); await page.click(el); el.dispatchEvent(new w.MouseEvent("dblclick", { bubbles: true, cancelable: true })); await page.settle(); },
    async contextmenu(target, init = {}) { page.el(target).dispatchEvent(new w.MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 10, clientY: 10, ...init })); await page.settle(); },
    async hover(target) { page.el(target).dispatchEvent(new w.MouseEvent("mouseenter", { bubbles: false })); await page.settle(5); },
    // a key or a chord ("mod+shift+p", "mod+k z"); returns whether the page took the key (preventDefault)
    async key(binding, target = null) {
      let taken = false;
      for (const stroke of binding.split(" ")) {
        const ev = new w.KeyboardEvent("keydown", keyInit(stroke, mac));
        (target ? page.el(target) : d.activeElement || d.body).dispatchEvent(ev);
        taken = ev.defaultPrevented;
        await page.settle(5);
      }
      await page.settle();
      return taken;
    },
    async type(target, text) {
      const el = page.el(target);
      el.focus();
      el.value = text;
      el.dispatchEvent(new w.Event("input", { bubbles: true }));
      await page.settle(80);
    },
    async run(id, ...args) { const r = page.eval(`runCommand(${JSON.stringify(id)}${args.map((a) => `, ${JSON.stringify(a)}`).join("")})`); await page.settle(); return r; },
    // drag with a fake DataTransfer: the page keeps what is dragged in its own variable, so the data is only a formality
    async drag(source, target, { at = null } = {}) {
      const data = {};
      const transfer = { types: [], effectAllowed: "all", dropEffect: "none", setData(k, v) { data[k] = v; if (!this.types.includes(k)) this.types.push(k); }, getData: (k) => data[k] ?? "", files: [] };
      const fire = (el, type) => {
        const ev = new w.Event(type, { bubbles: true, cancelable: true });
        Object.assign(ev, { dataTransfer: transfer, clientX: at?.x ?? 0, clientY: at?.y ?? 0, relatedTarget: null });
        el.dispatchEvent(ev);
        return ev;
      };
      const src = page.el(source), dst = page.el(target);
      fire(src, "dragstart");
      fire(dst, "dragenter");
      fire(dst, "dragover");
      const dropped = fire(dst, "drop");
      fire(src, "dragend");
      await page.settle();
      return dropped;
    },
    async ready() { await w.verdictReady; await page.settle(60); return page; },
    visible(target) { for (let el = page.el(target); el; el = el.parentElement) if (el.hidden) return false; return !!page.el(target); },
    close() { w.close(); },
  };
  openPages.push(page);
  return page;
}

module.exports = { openPage, closeAllPages, fixtureSession, loadJsdom, FILES, TREE, sleep };
