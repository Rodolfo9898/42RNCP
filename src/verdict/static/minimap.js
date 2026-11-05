"use strict";

// The minimap: a small picture of the whole file beside the editor, with a slider for the part you see. Click or drag on it to scroll.

const MINIMAP_WIDTH = 90;
// The colours are those of the syntax in the theme on show (--tok-k, --tok-s, ... in style.css).
const MINIMAP_TOKENS = ["k", "ty", "s", "n", "c", "pp", "f", "b", "v", "o", "h"];
function minimapColors() {
  const css = getComputedStyle(document.documentElement);
  const colors = { plain: css.getPropertyValue("--dim").trim() || "#9d9d9d" };
  for (const name of MINIMAP_TOKENS) colors[name] = css.getPropertyValue(`--tok-${name}`).trim() || colors.plain;
  return colors;
}

let canvasChecked = null;
function canvasSupported() {
  if (canvasChecked === null) {
    try { canvasChecked = !!document.createElement("canvas").getContext?.("2d"); } catch { canvasChecked = false; }
  }
  return canvasChecked;
}

function minimapFor(groupId) {
  const parts = groupEls.get(groupId);
  if (parts.minimap) return parts.minimap;
  const canvas = h("canvas", { class: "minimap-canvas", width: String(MINIMAP_WIDTH), height: "100" });
  const slider = h("div", { class: "minimap-slider" });
  const el = h("div", { class: "minimap", "aria-hidden": "true" }, canvas, slider);
  const scrollTo = (ev) => {
    const tab = tabs.get(editors.groups[groupId].active);
    if (!tab) return;
    const box = el.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (ev.clientY - box.top) / (box.height || 1)));
    tab.view.scrollTop = ratio * tab.view.scrollHeight - tab.view.clientHeight / 2;
  };
  el.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    scrollTo(ev);
    el.setPointerCapture?.(ev.pointerId);
    el.addEventListener("pointermove", scrollTo);
    el.addEventListener("lostpointercapture", () => el.removeEventListener("pointermove", scrollTo), { once: true });
  });
  parts.body.append(el);
  parts.minimap = { el, canvas, slider };
  return parts.minimap;
}

function renderMinimap(groupId) {
  const parts = groupEls.get(groupId);
  if (!parts) return;
  const tab = tabs.get(editors.groups[groupId]?.active);
  const want = settings.get("editor.minimap.enabled") && tab && tab.text && tab.codeEl && !tab.codeEl.hidden;
  if (!want) { if (parts.minimap) parts.minimap.el.hidden = true; return; }
  const map = minimapFor(groupId);
  map.el.hidden = false;
  const height = parts.body.clientHeight || 400;
  if (canvasSupported() && map.drawn !== `${tab.key}|${height}|${tab.text.length}`) {
    map.drawn = `${tab.key}|${height}|${tab.text.length}`;
    drawMinimap(map.canvas, tab, height);
  }
  updateMinimapSlider(groupId);
}

function drawMinimap(canvas, tab, height) {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = MINIMAP_WIDTH * ratio;
  canvas.height = height * ratio;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, MINIMAP_WIDTH, height);
  const colors = minimapColors();
  const lines = tab.text.split("\n");
  const rowHeight = Math.min(3, Math.max(0.5, height / lines.length));
  const step = Math.max(1, Math.ceil(lines.length / (height / 0.5)));                    // (a very long file: not every line is drawn)
  for (let i = 0; i < lines.length; i += step) {
    const y = (i / step) * Math.max(rowHeight, 1) * 1;
    if (y > height) break;
    let x = 0;
    const pairs = tab.tokens && tab.tokens.length === lines.length ? tab.tokens[i] : [[null, lines[i]]];
    for (const [cls, text] of pairs) {
      ctx.fillStyle = colors[cls] ?? colors.plain;
      for (const run of text.replace(/\t/g, "    ").match(/\s+|\S+/g) ?? []) {
        if (x >= MINIMAP_WIDTH) break;
        if (!/^\s/.test(run)) ctx.fillRect(x, y, Math.min(run.length, MINIMAP_WIDTH - x), Math.max(1, rowHeight - 0.5));
        x += run.length;
      }
    }
  }
}

function updateMinimapSlider(groupId) {
  const parts = groupEls.get(groupId);
  const map = parts?.minimap;
  const tab = tabs.get(editors.groups[groupId]?.active);
  if (!map || !tab || map.el.hidden) return;
  const total = tab.view.scrollHeight || 1, visible = tab.view.clientHeight || 1;
  const box = map.el.clientHeight || parts.body.clientHeight || 1;
  map.slider.style.top = `${(tab.view.scrollTop / total) * box}px`;
  map.slider.style.height = `${Math.min(1, visible / total) * box}px`;
}

bus.on("group:rendered", renderMinimap);
bus.on("fileview:scroll", (path) => { const g = groupOf(path); if (g && editors.groups[g].active === path) updateMinimapSlider(g); });
bus.on("fileview:mode", (path) => { const g = groupOf(path); if (g) renderMinimap(g); });
bus.on("setting", (id) => { if (id === "editor.minimap.enabled") for (const g of groupEls.keys()) renderMinimap(g); });
// A window or a divider being resized fires "fit" many times a second: the minimaps are drawn again once per frame.
let minimapFrame = 0;
const redrawMinimaps = () => {
  minimapFrame = 0;
  for (const g of groupEls.keys()) { const parts = groupEls.get(g); if (parts.minimap) parts.minimap.drawn = ""; renderMinimap(g); }
};
bus.on("fit", () => { if (!minimapFrame) minimapFrame = requestAnimationFrame(redrawMinimaps); });           // (a new colour theme says "fit" too: the colours are read when drawing)
