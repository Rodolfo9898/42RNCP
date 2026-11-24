"use strict";

// A subject PDF opened in the editor: the pages of the PDF as images, one under the other, scrolled like any document.
//  - A click on a subject of the Subjects view opens it; a click on "From push_swap.pdf, page 3" of a check opens it at that page.
//  - The pages come from the web app (the same images the old browser UI showed), one at a time and only when they are near the
//    screen, so a 40-page subject opens at once. The page is plain images: no PDF is ever run, and the page has no way to reach the
//    network (its content security policy allows nothing but its own script and the images it is handed).
//  - One tab per PDF: opening it again goes to that tab, at the page asked for.

const vscode = require("vscode");
const crypto = require("crypto");

const MAX_PAGES = 400;
const panels = new Map();           // subject name -> its tab

const pageOf = (value, pages) => Math.min(Math.max(Number.isInteger(Number(value)) ? Number(value) : 1, 1), pages);

// What runs inside the tab. (A string, not a file: it has to be inlined, with the nonce, to be allowed to run.)
const PAGE_SCRIPT = `
const vscode = acquireVsCodeApi();
const pagesBox = document.getElementById("pages");
const jump = document.getElementById("jump");
const total = document.getElementById("total");
const zoom = document.getElementById("zoom");
const figures = [];
const asked = new Set();
total.textContent = String(CONFIG.pages);
jump.max = String(CONFIG.pages);

const near = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    const n = Number(entry.target.dataset.n);
    if (entry.isIntersecting && !asked.has(n)) { asked.add(n); vscode.postMessage({ t: "page", n }); }
  }
}, { rootMargin: "900px 0px" });

for (let n = 1; n <= CONFIG.pages; n++) {
  const figure = document.createElement("figure");
  figure.dataset.n = String(n);
  const image = document.createElement("img");
  image.alt = "Page " + n;
  figure.append(image);
  const caption = document.createElement("figcaption");
  caption.textContent = n + " / " + CONFIG.pages;
  figure.append(caption);
  pagesBox.append(figure);
  figures.push({ figure, image, caption });
  near.observe(figure);
}

function go(n) {
  const target = figures[Math.min(Math.max(n, 1), CONFIG.pages) - 1];
  if (target) target.figure.scrollIntoView({ block: "start" });
}

function current() {
  const i = figures.findIndex(({ figure }) => figure.getBoundingClientRect().bottom > window.innerHeight * 0.35);
  return i < 0 ? CONFIG.pages : i + 1;
}

let ticking = false;
window.addEventListener("scroll", () => {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => { ticking = false; if (document.activeElement !== jump) jump.value = String(current()); });
});
jump.addEventListener("change", () => go(Number(jump.value)));
zoom.addEventListener("change", () => { const keep = current(); document.documentElement.style.setProperty("--w", zoom.value); go(keep); });

window.addEventListener("message", ({ data }) => {
  if (!data) return;
  if (data.t === "page" && figures[data.n - 1]) {
    const { image, figure } = figures[data.n - 1];
    image.src = data.src;
    figure.classList.add("loaded");
  } else if (data.t === "error" && figures[data.n - 1]) {
    figures[data.n - 1].caption.textContent = data.n + " / " + CONFIG.pages + " - " + data.text;
    figures[data.n - 1].figure.classList.add("failed");
  } else if (data.t === "goto") {
    go(data.page);
  }
});
jump.value = String(CONFIG.page);
go(CONFIG.page);
`;

const PAGE_STYLE = `
:root { --w: 100%; }
body { margin: 0; padding: 0 0 40px; background: var(--vscode-editor-background, #1e1e1e); color: var(--vscode-editor-foreground, #cccccc); font-family: var(--vscode-font-family, sans-serif); }
#bar { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 10px; padding: 6px 14px; background: var(--vscode-editorWidget-background, #252526);
  border-bottom: 1px solid var(--vscode-editorWidget-border, transparent); font-size: 12px; }
#bar .name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#bar .spacer { flex: 1; }
#bar input, #bar select { background: var(--vscode-input-background, #3c3c3c); color: var(--vscode-input-foreground, #cccccc); border: 1px solid var(--vscode-input-border, #555); padding: 2px 4px; }
#bar input { width: 54px; }
figure { margin: 14px auto 0; width: var(--w); max-width: none; }
figure img { display: block; width: 100%; aspect-ratio: 1 / 1.414; background: #ffffff; box-shadow: 0 1px 6px #0008; }
figure.loaded img { aspect-ratio: auto; }
figure.failed img { background: var(--vscode-inputValidation-errorBackground, #5a1d1d); }
figcaption { text-align: center; opacity: 0.6; font-size: 11px; padding: 4px 0; }
`;

function pageHtml(nonce, config) {
  const data = JSON.stringify(config).replace(/</g, "\\u003c");     // the name comes from a file name: it cannot close the script
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
<style nonce="${nonce}">${PAGE_STYLE}</style></head>
<body>
<div id="bar"><span class="name" id="name"></span><span class="spacer"></span>
<label>Page <input id="jump" type="number" min="1" value="1"> / <span id="total"></span></label>
<select id="zoom" title="Zoom"><option value="100%">Fit width</option><option value="600px">600 px</option><option value="800px">800 px</option><option value="1000px">1000 px</option><option value="1400px">1400 px</option></select></div>
<div id="pages"></div>
<script nonce="${nonce}">const CONFIG = ${data}; document.getElementById("name").textContent = CONFIG.name;</script>
<script nonce="${nonce}">${PAGE_SCRIPT}</script>
</body></html>`;
}

/** Open (or go to) the PDF of a subject of the review. `deps`: session() and fetchPage(name, n) -> Buffer. */
async function open(deps, name, page) {
  const subject = (deps.session()?.subjects || []).find((s) => s.name === name);
  if (!subject) throw new Error(`${name || "that PDF"} is not a subject of this review`);
  const pages = Math.min(Number(subject.pages) || 0, MAX_PAGES);
  if (!pages) throw new Error(`${name} has no pages to show`);
  const target = pageOf(page, pages);

  const existing = panels.get(name);
  if (existing) {
    existing.reveal();
    existing.webview.postMessage({ t: "goto", page: target });
    return;
  }
  const panel = vscode.window.createWebviewPanel("verdict.subject", name, vscode.ViewColumn.Active,
    { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [] });
  panel.iconPath = undefined;
  panels.set(name, panel);
  panel.onDidDispose(() => { if (panels.get(name) === panel) panels.delete(name); });
  panel.webview.onDidReceiveMessage(async (message) => {
    if (!message || message.t !== "page" || !Number.isInteger(message.n) || message.n < 1 || message.n > pages) return;
    try {
      const png = await deps.fetchPage(name, message.n);
      panel.webview.postMessage({ t: "page", n: message.n, src: `data:image/png;base64,${png.toString("base64")}` });
    } catch (err) {
      panel.webview.postMessage({ t: "error", n: message.n, text: String(err.message || err).slice(0, 200) });
    }
  });
  panel.webview.html = pageHtml(crypto.randomBytes(16).toString("hex"), { name, pages, page: target });
}

/** After the review's subjects changed: a tab of a subject that is gone is closed. */
function sync(session) {
  const have = new Set((session?.subjects || []).map((s) => s.name));
  for (const [name, panel] of [...panels]) if (!have.has(name)) panel.dispose();
}

function activate(ctx, deps) {
  ctx.subscriptions.push(vscode.commands.registerCommand("verdict.openSubject", async (arg, page) => {
    const name = typeof arg === "string" ? arg : arg?.subject;
    try {
      await open(deps, name, page);
    } catch (err) {
      vscode.window.showErrorMessage(`Verdict: ${err.message}`);
    }
  }));
}

module.exports = { activate, open, sync, pageHtml, MAX_PAGES };
