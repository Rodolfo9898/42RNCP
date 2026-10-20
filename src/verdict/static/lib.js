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

if (typeof module !== "undefined") {
  module.exports = { h, appendNodes, inlineMarkdown, renderMarkdown, renderBlocks, parseLink, defaultViewMode, isMarkdownPath, rainbow, rainbowEnabled, RAINBOW_LEVELS };
}
