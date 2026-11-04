// Runs src/verdict/static/lib.js under Node with a tiny fake DOM, for tests/test_frontend.py.
//   node harness.js markdown   < markdown text      -> the rendered tree as an HTML-like string
//   node harness.js rainbow    < json token lines   -> json
//   node harness.js mode       < json [path, line]  -> the default view mode
const fs = require("fs");
const path = require("path");

class Node {}
class Text extends Node {
  constructor(text) { super(); this.nodeType = 3; this.data = text; }
  get textContent() { return this.data; }
}
class Element extends Node {
  constructor(tag) { super(); this.nodeType = 1; this.tagName = tag; this.attrs = {}; this.childNodes = []; }
  set className(value) { this.attrs.class = value; }
  get className() { return this.attrs.class || ""; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  addEventListener() {}
  append(...items) { for (const item of items) this.childNodes.push(item instanceof Node ? item : new Text(String(item))); }
  get children() { return this.childNodes.filter((n) => n.nodeType === 1); }
  get textContent() { return this.childNodes.map((n) => n.textContent).join(""); }
}
global.Node = Node;
global.document = { createElement: (tag) => new Element(tag), createTextNode: (text) => new Text(text) };

const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
function serialize(node) {
  if (node.nodeType === 3) return escape(node.data);
  const attrs = Object.entries(node.attrs).map(([k, v]) => ` ${k}="${escape(v)}"`).join("");
  return `<${node.tagName}${attrs}>${node.childNodes.map(serialize).join("")}</${node.tagName}>`;
}

const lib = require(path.join(__dirname, "../../src/verdict/static/lib.js"));
const input = fs.readFileSync(0, "utf8");
const [command] = process.argv.slice(2);
if (command === "markdown") process.stdout.write(serialize(lib.renderMarkdown(input)));
else if (command === "rainbow") process.stdout.write(JSON.stringify(lib.rainbow(JSON.parse(input))));
else if (command === "mode") { const [p, line] = JSON.parse(input); process.stdout.write(lib.defaultViewMode(p, line)); }
else if (command === "append") {
  const parent = document.createElement("div");
  const build = (x) => (Array.isArray(x) ? x.map(build) : (x && x.el ? lib.h(x.el, {}, x.text) : x));
  lib.appendNodes(parent, ...build(JSON.parse(input)));
  process.stdout.write(serialize(parent));
} else if (command === "enabled") process.stdout.write(JSON.stringify(JSON.parse(input).map(lib.rainbowEnabled)));
else if (command === "fuzzy") process.stdout.write(JSON.stringify(JSON.parse(input).map(([query, text]) => lib.fuzzyMatch(query, text))));
else if (command === "key") process.stdout.write(JSON.stringify(JSON.parse(input).map(([ev, binding, mac]) => lib.matchesKey(ev, binding, mac))));
else if (command === "showkey") process.stdout.write(JSON.stringify(JSON.parse(input).map(([binding, mac]) => lib.showKey(binding, mac))));
else if (command === "close") { const [entries, mode, key] = JSON.parse(input); process.stdout.write(JSON.stringify(lib.tabsToClose(entries, mode, key))); }
else if (command === "move") { const [keys, from, to, after] = JSON.parse(input); process.stdout.write(JSON.stringify(lib.moveKey(keys, from, to, after))); }
else if (command === "decided") process.stdout.write(JSON.stringify(JSON.parse(input).map(lib.decidedNote)));
else if (command === "sshnote") process.stdout.write(JSON.stringify(JSON.parse(input).map(lib.sshNote)));
else { console.error("unknown command"); process.exit(2); }
