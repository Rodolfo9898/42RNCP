// Runs the REAL ⬇ Apply to project dialog code (extracted from app.js) under Node, with a small fake DOM that supports clicks and
// checkboxes, and canned answers from the API. For tests/test_frontend.py.
//   node apply_dialog.js < json {"data": <GET .../changes>, "result": <POST .../changes/apply>, "ticks": {"review": bool, "files": [bool]}, "press": bool}
//   -> json: what the dialog shows, and (when "press") what pressing Apply sent and said.
const fs = require("fs");
const path = require("path");

class FakeNode {}
class FakeText extends FakeNode {
  constructor(text) { super(); this.nodeType = 3; this.data = text; }
  get textContent() { return this.data; }
}
class FakeElement extends FakeNode {
  constructor(tag) { super(); this.nodeType = 1; this.tagName = tag; this.attrs = {}; this.childNodes = []; this.handlers = {}; this.checked = false; this.disabled = false; }
  set className(value) { this.attrs.class = value; }
  get className() { return this.attrs.class || ""; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); }
  set onclick(fn) { this.addEventListener("click", fn); }
  append(...items) { for (const item of items) this.childNodes.push(item instanceof FakeNode ? item : new FakeText(String(item))); }
  replaceChildren(...items) { this.childNodes = []; this.append(...items); }
  get textContent() { return this.childNodes.map((n) => n.textContent).join(""); }
  set textContent(value) { this.childNodes = [new FakeText(String(value))]; }
  async click() { for (const fn of this.handlers.click || []) await fn({ preventDefault() {}, stopPropagation() {} }); }
  change(checked) { this.checked = checked; for (const fn of this.handlers.change || []) fn({}); }
}
global.Node = FakeNode;
global.document = { createElement: (tag) => new FakeElement(tag), createTextNode: (text) => new FakeText(text) };

const walk = (node, visit) => { visit(node); (node.childNodes || []).forEach((child) => walk(child, visit)); };
const find = (node, test) => { const found = []; walk(node, (n) => { if (n.nodeType === 1 && test(n)) found.push(n); }); return found; };
const hasClass = (n, name) => (n.className || "").split(/\s+/).includes(name);

const lib = require(path.join(__dirname, "../../src/verdict/static/lib.js"));
const source = fs.readFileSync(path.join(__dirname, "../../src/verdict/static/app.js"), "utf8");
const code = source.slice(source.indexOf("const CHANGE_CHIP"), source.indexOf("function renderPanel() {"));
if (!code.includes("async function openChanges")) { console.error("openChanges not found in app.js"); process.exit(2); }

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const seen = { dialog: null, post: null, toast: null, calls: { render: 0, loadTree: 0, refreshVerdict: 0, closeDialog: 0 } };
Object.assign(global, {
  h: lib.h,
  sid: "sess123",
  session: { repo: { path: input.data.project || "libft" } },
  api: async (p) => (p.startsWith("sessions/sess123/changes") ? input.data : { repo: { path: "libft" } }),
  post: async (p, body) => { seen.post = { path: p, body }; return input.result; },
  toast: (message, ok = false) => { seen.toast = { message, ok }; },
  dialog: (title, body, buttons) => { seen.dialog = { title, body, buttons }; },
  closeDialog: () => { seen.calls.closeDialog += 1; },
  guarded: (fn) => fn(),
  render: () => { seen.calls.render += 1; },
  loadTree: () => { seen.calls.loadTree += 1; },
  refreshVerdict: () => { seen.calls.refreshVerdict += 1; return Promise.resolve(); },
});
const openChanges = new Function(`${code}\nreturn openChanges;`)();

(async () => {
  await openChanges();
  const { title, body, buttons } = seen.dialog;
  const checkboxes = find(body, (n) => n.tagName === "input");
  const reviewBox = find(body, (n) => hasClass(n, "review"))[0]?.childNodes.flatMap((n) => find(n, (x) => x.tagName === "input"))[0];
  const rowOf = (box) => find(body, (n) => hasClass(n, "change") && find(n, (x) => x === box).length > 0).pop();
  const noteOf = (row) => find(row, (n) => hasClass(n, "note"))[0]?.textContent || "";
  const applyButton = buttons.find((b) => b.className.includes("primary"));
  const describe = () => ({ text: applyButton.textContent, disabled: applyButton.disabled });
  const out = {
    title,
    intro: find(body, (n) => n.tagName === "p").map((n) => n.textContent),
    review: reviewBox ? { checked: reviewBox.checked, disabled: reviewBox.disabled, label: find(rowOf(reviewBox), (n) => n.tagName === "strong")[0].textContent, note: noteOf(rowOf(reviewBox)) } : null,
    files: checkboxes.filter((b) => b !== reviewBox).map((b) => ({ path: find(rowOf(b), (n) => hasClass(n, "name"))[0].textContent, checked: b.checked, disabled: b.disabled, note: noteOf(rowOf(b)) })),
    apply: describe(),
  };
  if (input.ticks) {
    if (typeof input.ticks.review === "boolean" && reviewBox) reviewBox.change(input.ticks.review);
    (input.ticks.files || []).forEach((on, i) => { if (typeof on === "boolean") checkboxes.filter((b) => b !== reviewBox)[i].change(on); });
    out.applyAfterTicks = describe();
  }
  if (input.press) {
    await applyButton.click();
    out.sent = seen.post; out.toast = seen.toast; out.calls = seen.calls;
  }
  console.log(JSON.stringify(out));
})().catch((err) => { console.error(err); process.exit(1); });
