"use strict";

// Helpers shared by the interface and by its tests (Node loads this file too, see the bottom).
// Everything shown comes from untrusted input (PDFs, repositories): build DOM with textContent only, never innerHTML.

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

// Like el.append(...) but skips null/undefined/false (the DOM would write the word "null" into the page) and flattens arrays.
function appendNodes(parent, ...items) {
  for (const item of items.flat(Infinity)) {
    if (item == null || item === false) continue;
    parent.append(item instanceof Node ? item : document.createTextNode(String(item)));
  }
  return parent;
}

// ------------------------------------------------------------------ markdown (safe: DOM nodes only, no HTML is ever interpreted)

const SAFE_LINK = /^(https?:\/\/|mailto:)/i;
const PUNCTUATION = /[!-/:-@[-`{-~]/;

// [text](url "title") starting at source[start] === "[" -> { text, url, title, end } or null
function parseLink(source, start) {
  let depth = 0, i = start;
  for (; i < source.length; i++) {
    if (source[i] === "\\") { i++; continue; }
    if (source[i] === "[") depth++;
    else if (source[i] === "]" && --depth === 0) break;
  }
  if (depth !== 0 || source[i + 1] !== "(") return null;
  const text = source.slice(start + 1, i);
  let j = i + 2, parens = 1;
  for (; j < source.length; j++) {
    if (source[j] === "\\") { j++; continue; }
    if (source[j] === "(") parens++;
    else if (source[j] === ")" && --parens === 0) break;
  }
  if (parens !== 0) return null;
  const inside = source.slice(i + 2, j).trim();
  const m = inside.match(/^<?([^\s>]*)>?(?:\s+["']([^"']*)["'])?$/);
  return m ? { text, url: m[1], title: m[2] || "", end: j + 1 } : null;
}

function linkNode(url, title, children) {
  if (!SAFE_LINK.test(url)) {                        // relative paths, anchors, javascript: ... are shown, never followed
    return h("span", { class: "md-link-plain", title: url || null }, children);
  }
  return h("a", { href: url, target: "_blank", rel: "noopener noreferrer nofollow", title: title || url }, children);
}

function inlineMarkdown(source) {
  const out = [];
  let buffer = "";
  const flush = () => { if (buffer) { out.push(buffer); buffer = ""; } };
  let i = 0;
  while (i < source.length) {
    const c = source[i];
    if (c === "\\" && i + 1 < source.length && PUNCTUATION.test(source[i + 1])) { buffer += source[i + 1]; i += 2; continue; }
    if (c === "`") {
      const ticks = source.slice(i).match(/^`+/)[0];
      const end = source.indexOf(ticks, i + ticks.length);
      if (end > -1) {
        flush();
        out.push(h("code", {}, source.slice(i + ticks.length, end).trim()));
        i = end + ticks.length;
        continue;
      }
    }
    if (c === "!" && source[i + 1] === "[") {           // images are never loaded (a README must not make the app fetch things)
      const link = parseLink(source, i + 1);
      if (link) { flush(); out.push(h("span", { class: "md-image", title: link.url }, `🖼 ${link.text || "image"}`)); i = link.end; continue; }
    }
    if (c === "[") {
      const link = parseLink(source, i);
      if (link) { flush(); out.push(linkNode(link.url, link.title, inlineMarkdown(link.text))); i = link.end; continue; }
    }
    if (c === "<") {
      const auto = source.slice(i).match(/^<((?:https?:\/\/|mailto:)[^\s<>]+)>/i);
      if (auto) { flush(); out.push(linkNode(auto[1], "", auto[1])); i += auto[0].length; continue; }
    }
    if (source.startsWith("**", i)) {
      const end = source.indexOf("**", i + 2);
      if (end > i + 2) { flush(); out.push(h("strong", {}, inlineMarkdown(source.slice(i + 2, end)))); i = end + 2; continue; }
    }
    if (source.startsWith("~~", i)) {
      const end = source.indexOf("~~", i + 2);
      if (end > i + 2) { flush(); out.push(h("del", {}, inlineMarkdown(source.slice(i + 2, end)))); i = end + 2; continue; }
    }
    if (source.startsWith("__", i) && (i === 0 || /[\s(]/.test(source[i - 1]))) {
      const end = source.indexOf("__", i + 2);
      if (end > i + 2 && !/\s/.test(source[i + 2])) { flush(); out.push(h("strong", {}, inlineMarkdown(source.slice(i + 2, end)))); i = end + 2; continue; }
    }
    if (c === "*" && source[i + 1] !== "*" && source[i + 1] && !/\s/.test(source[i + 1])) {
      let end = i + 1;
      while ((end = source.indexOf("*", end)) > -1 && (source[end - 1] === "\\" || /\s/.test(source[end - 1]) || source[end + 1] === "*")) end++;
      if (end > i + 1) { flush(); out.push(h("em", {}, inlineMarkdown(source.slice(i + 1, end)))); i = end + 1; continue; }
    }
    if (c === "_" && (i === 0 || /[\s(]/.test(source[i - 1])) && source[i + 1] && !/\s/.test(source[i + 1])) {
      let end = i + 1;
      while ((end = source.indexOf("_", end)) > -1 && (source[end - 1] === "\\" || /\s/.test(source[end - 1]))) end++;
      if (end > -1) { flush(); out.push(h("em", {}, inlineMarkdown(source.slice(i + 1, end)))); i = end + 1; continue; }
    }
    buffer += c;
    i++;
  }
  flush();
  return out;
}

const FENCE = /^(\s*)(`{3,}|~{3,})(.*)$/;
const HR = /^ {0,3}([-*_])(?:\s*\1){2,}\s*$/;
const BULLET = /^(\s*)([-*+])\s+(.*)$/;
const ORDERED = /^(\s*)(\d{1,9})[.)]\s+(.*)$/;
const indentWidth = (line) => line.match(/^[ \t]*/)[0].replace(/\t/g, "    ").length;

function renderBlocks(lines) {
  const out = [];
  const isBlockStart = (line, next) =>
    FENCE.test(line) || /^ {0,3}#{1,6}\s/.test(line) || HR.test(line) || /^ {0,3}>/.test(line)
    || BULLET.test(line) || /^\s*1[.)]\s+/.test(line) || (line.trim().startsWith("|") && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(next || ""));
  const takeFence = (start) => {
    const open = lines[start].match(FENCE);
    const fence = open[2], indent = open[1].length;
    const body = [];
    let j = start + 1;
    while (j < lines.length) {
      const close = lines[j].match(/^\s*(`{3,}|~{3,})\s*$/);
      if (close && close[1][0] === fence[0] && close[1].length >= fence.length) break;
      body.push(lines[j].slice(Math.min(indent, indentWidth(lines[j]))));
      j++;
    }
    return { node: h("pre", { class: "log", "data-lang": open[3].trim().split(/\s+/)[0] || null }, body.join("\n")), next: j + 1 };
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim() || /^\s*<!--.*-->\s*$/.test(line)) { i++; continue; }
    if (FENCE.test(line)) { const { node, next } = takeFence(i); out.push(node); i = next; continue; }

    const heading = line.match(/^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/);
    if (heading) { out.push(h(`h${heading[1].length}`, {}, inlineMarkdown(heading[2]))); i++; continue; }
    if (HR.test(line)) { out.push(h("hr")); i++; continue; }

    if (line.trim().startsWith("|") && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1] || "")) {
      const cells = (l) => l.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim());
      const head = cells(line), rows = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]));
      out.push(h("table", {}, h("thead", {}, h("tr", {}, head.map((c) => h("th", {}, inlineMarkdown(c))))),
        h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, inlineMarkdown(c))))))));
      continue;
    }

    if (/^ {0,3}>/.test(line)) {
      const inner = [];
      while (i < lines.length && /^ {0,3}>/.test(lines[i])) inner.push(lines[i++].replace(/^ {0,3}> ?/, ""));
      out.push(h("blockquote", {}, renderBlocks(inner)));
      continue;
    }

    if (BULLET.test(line) || ORDERED.test(line)) {
      const top = { indent: -1, list: h("div"), last: null, kind: "root" };
      const stack = [top];
      const itemOf = (l) => {
        const b = l.match(BULLET), o = !b && l.match(ORDERED);
        if (b && !HR.test(l)) return { indent: indentWidth(l), kind: "ul", text: b[3] };
        if (o) return { indent: indentWidth(l), kind: "ol", text: o[3], start: Number(o[2]) };
        return null;
      };
      while (i < lines.length) {
        const current = lines[i];
        const item = itemOf(current);
        if (!current.trim()) {                                  // a blank line only ends the list if no item follows
          let k = i + 1;
          while (k < lines.length && !lines[k].trim()) k++;
          if (k < lines.length && (itemOf(lines[k]) || (FENCE.test(lines[k]) && indentWidth(lines[k]) >= 2 && stack.at(-1).last))) { i = k; continue; }
          break;
        }
        if (FENCE.test(current) && stack.at(-1).last && indentWidth(current) >= 2) {
          const { node, next } = takeFence(i);
          stack.at(-1).last.append(node);
          i = next;
          continue;
        }
        if (!item) {                                            // a continuation line of the last item (lazy or indented)
          if (isBlockStart(current, lines[i + 1]) && indentWidth(current) < 2) break;
          const last = stack.at(-1).last;
          if (!last) break;
          last.append(" ", ...inlineMarkdown(current.trim()));
          i++;
          continue;
        }
        while (stack.length > 1 && stack.at(-1).indent > item.indent) stack.pop();
        let level = stack.at(-1);
        if (level.indent < item.indent && level.last) {         // deeper than the previous item: a nested list
          const sub = h(item.kind, item.kind === "ol" && item.start !== 1 ? { start: item.start } : {});
          level.last.append(sub);
          level = { indent: item.indent, list: sub, last: null, kind: item.kind };
          stack.push(level);
        } else if (level.kind !== item.kind && level.kind !== "root") {
          const sub = h(item.kind, item.kind === "ol" && item.start !== 1 ? { start: item.start } : {});
          const parent = stack.at(-2);
          (parent && parent.last ? parent.last : top.list).append(sub);
          stack.pop();
          level = { indent: item.indent, list: sub, last: null, kind: item.kind };
          stack.push(level);
        } else if (level.kind === "root") {
          const first = h(item.kind, item.kind === "ol" && item.start !== 1 ? { start: item.start } : {});
          top.list.append(first);
          level = { indent: item.indent, list: first, last: null, kind: item.kind };
          stack.push(level);
        }
        const task = item.text.match(/^\[([ xX])\]\s+(.*)$/);
        const li = h("li", {}, task ? [task[1] === " " ? "☐ " : "☑ ", inlineMarkdown(task[2])] : inlineMarkdown(item.text));
        level.list.append(li);
        level.last = li;
        i++;
      }
      out.push(...top.list.children);
      continue;
    }

    const para = [line.trim()];
    i++;
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i], lines[i + 1])
           && !(para.length === 1 && /^ {0,3}=+\s*$/.test(lines[i]))) para.push(lines[i++].trim());     // "=====" underlines a heading
    const setext = para.length === 1 && lines[i] && /^ {0,3}(=+|-+)\s*$/.test(lines[i]) ? lines[i].trim()[0] : null;
    if (setext) { i++; out.push(h(setext === "=" ? "h1" : "h2", {}, inlineMarkdown(para[0]))); continue; }
    out.push(h("p", {}, inlineMarkdown(para.join(" "))));
  }
  return out;
}

function renderMarkdown(text) {
  return h("div", { class: "markdown" }, renderBlocks(text.split("\n")));
}

// A markdown file opens rendered; a "file:line" reference opens the code, because a line number only means something there.
function defaultViewMode(path, line) {
  return /\.(md|markdown)$/i.test(path) && !line ? "preview" : "code";
}

const isMarkdownPath = (path) => /\.(md|markdown)$/i.test(path);

// ------------------------------------------------------------------ rainbow brackets

const RAINBOW_LEVELS = 6;
const OPENERS = "([{", CLOSERS = ")]}";
const NO_RAINBOW_LANGUAGES = new Set(["markdown", "restructuredtext", "text only", "diff", "csv"]);

const rainbowEnabled = (language) => !!language && !NO_RAINBOW_LANGUAGES.has(String(language).toLowerCase());

// tokens: [[cls, text], ...] per line  ->  the same, with brackets split out as [cls, bracket, level].
// level 0..5 cycles with the nesting depth; -1 marks a bracket with no partner. Strings and comments are left alone.
function rainbow(lines, skip = new Set(["s", "c"])) {
  const stack = [];
  const result = lines.map((line) => {
    const pieces = [];
    for (const token of line) {
      const [cls, text] = token;
      if (skip.has(cls) || !/[()[\]{}]/.test(text)) { pieces.push(token); continue; }
      let plain = "";
      for (const ch of text) {
        const open = OPENERS.indexOf(ch), close = CLOSERS.indexOf(ch);
        if (open === -1 && close === -1) { plain += ch; continue; }
        if (plain) { pieces.push([cls, plain]); plain = ""; }
        if (open !== -1) {
          const piece = [cls, ch, stack.length % RAINBOW_LEVELS];
          stack.push({ kind: open, piece });
          pieces.push(piece);
        } else if (stack.length && stack[stack.length - 1].kind === close) {
          pieces.push([cls, ch, stack.pop().piece[2]]);
        } else {
          pieces.push([cls, ch, -1]);
        }
      }
      if (plain) pieces.push([cls, plain]);
    }
    return pieces;
  });
  for (const { piece } of stack) piece[2] = -1;          // openers that never closed
  return result;
}

// ------------------------------------------------------------------ workbench helpers (keys, fuzzy search, tab order): pure, so Node tests them

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

const isWordStart = (text, i) => i === 0 || "/\\._- ".includes(text[i - 1]) || (/[A-Z]/.test(text[i]) && /[a-z]/.test(text[i - 1]));

// VS Code's fuzzy matching: every character of `query` must be in `text`, in order, and the best alignment wins. A match at the
// start of a word (after / . _ - or a space, or a capital) and a match right after the previous one score higher, so "fr" finds
// the start of "frontend.js" rather than the first f and r it meets. Returns null, or { score, positions } (the matched indexes).
function fuzzyMatch(query, text) {
  const wanted = query.replace(/\s+/g, "");
  if (!wanted) return { score: 0, positions: [] };
  const q = wanted.toLowerCase(), t = text.toLowerCase(), m = q.length, n = t.length;
  if (m > n) return null;
  let k = 0;
  for (const ch of t) if (ch === q[k] && ++k === m) break;
  if (k < m) return null;                                         // not even a subsequence
  const best = Array.from({ length: m }, () => new Array(n).fill(-Infinity));
  const prev = Array.from({ length: m }, () => new Array(n).fill(-1));
  const upTo = Array.from({ length: m }, () => new Array(n).fill(-1));   // the position <= j with the best score in row i
  for (let i = 0; i < m; i++) {
    for (let j = i; j < n; j++) {
      if (t[j] === q[i]) {
        const gain = 1 + (isWordStart(text, j) ? 5 : 0) + (text[j] === wanted[i] ? 1 : 0);
        if (i === 0) {
          best[i][j] = gain - j * 0.02;                             // (earlier is slightly better)
        } else {
          let score = -Infinity, from = -1;
          if (j >= 1 && best[i - 1][j - 1] > -Infinity) { score = best[i - 1][j - 1] + gain + 8; from = j - 1; }     // right after the previous match: worth more than a word start
          const p = j >= 2 ? upTo[i - 1][j - 2] : -1;
          if (p >= 0 && best[i - 1][p] + gain > score) { score = best[i - 1][p] + gain; from = p; }
          best[i][j] = score;
          prev[i][j] = from;
        }
      }
      const last = j > 0 ? upTo[i][j - 1] : -1;
      upTo[i][j] = last >= 0 && best[i][last] >= best[i][j] ? last : (best[i][j] > -Infinity ? j : last);
    }
  }
  let end = upTo[m - 1][n - 1];
  if (end < 0 || best[m - 1][end] === -Infinity) return null;
  const positions = [];
  for (let i = m - 1, j = end; i >= 0; i--) { positions.unshift(j); j = prev[i][j]; }
  return { score: best[m - 1][end] - n * 0.01, positions };
}

// Does keyboard event `ev` match a binding such as "mod+shift+p", "ctrl+`", "alt+w" or "f1"? "mod" is Cmd on a Mac and Ctrl elsewhere.
// The physical key is accepted too (Alt changes the character on a Mac, and the key under Esc is ² on a Belgian keyboard).
function matchesKey(ev, binding, isMac) {
  const parts = binding.toLowerCase().split("+");
  const key = parts.pop();
  const want = { ctrl: false, meta: false, alt: false, shift: false };
  for (const part of parts) want[part === "mod" ? (isMac ? "meta" : "ctrl") : part] = true;
  if (!!ev.ctrlKey !== want.ctrl || !!ev.metaKey !== want.meta || !!ev.altKey !== want.alt || !!ev.shiftKey !== want.shift) return false;
  const typed = String(ev.key || "").toLowerCase(), code = String(ev.code || "");
  if (key === "`") return typed === "`" || code === "Backquote";
  if (/^[a-z]$/.test(key)) return typed === key || code === `Key${key.toUpperCase()}`;
  return typed === key || code.toLowerCase() === key;
}

// How a binding is shown: "⇧⌘P" on a Mac, "Ctrl+Shift+P" elsewhere.
function showKey(binding, isMac) {
  const parts = binding.split("+");
  const key = parts.pop();
  const label = key.length === 1 ? key.toUpperCase() : key[0].toUpperCase() + key.slice(1);
  const names = { mod: isMac ? "⌘" : "Ctrl", ctrl: isMac ? "⌃" : "Ctrl", alt: isMac ? "⌥" : "Alt", shift: isMac ? "⇧" : "Shift", meta: isMac ? "⌘" : "Meta" };
  const order = isMac ? ["ctrl", "alt", "shift", "mod", "meta"] : ["ctrl", "mod", "meta", "alt", "shift"];     // (the order each platform writes them in)
  const shown = order.filter((name) => parts.map((p) => p.toLowerCase()).includes(name)).map((name) => names[name]);
  return isMac ? shown.join("") + label : [...shown, label].join("+");
}

// Which tabs "Close Others", "Close to the Right" and "Close All" close. entries: [{ key, closable, session }] in tab order. A session
// (claude, the shell) is a running conversation, not a document: closing it ends it, so these never close one.
function tabsToClose(entries, mode, key) {
  const at = entries.findIndex((e) => e.key === key);
  return entries.filter((e, i) => e.closable && !e.session
    && (mode === "all" || (mode === "others" && e.key !== key) || (mode === "right" && i > at))).map((e) => e.key);
}

// The order of the tabs after dragging `from` onto `to` (dropped on its left half, or its right half when `after`).
function moveKey(keys, from, to, after = false) {
  if (from === to || !keys.includes(from) || !keys.includes(to)) return keys.slice();
  const rest = keys.filter((k) => k !== from);
  rest.splice(rest.indexOf(to) + (after ? 1 : 0), 0, from);
  return rest;
}

if (typeof module !== "undefined") {
  module.exports = { fuzzyMatch, matchesKey, showKey, tabsToClose, moveKey, h, appendNodes, inlineMarkdown, renderMarkdown, renderBlocks, parseLink, defaultViewMode, isMarkdownPath, rainbow, rainbowEnabled, RAINBOW_LEVELS };
}
