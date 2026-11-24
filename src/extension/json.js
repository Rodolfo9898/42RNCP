"use strict";

// JSON that can be read. A file saved on one line (an export, a minified config) is opened by the extension as a pretty-printed
// view, read-only, and never written back: the file on disk is not touched. No vscode here (see extension.js for the editor side).

const MAX_BYTES = 2 * 1024 * 1024;
const LONG_LINE = 160;

// The same JSON, one value per line, indented. The text of every number and string is kept exactly as it is (no rounding of big
// numbers, keys in the file's order). Returns null when `text` is not JSON.
function pretty(text, unit = "  ") {
  const src = text.replace(/^\uFEFF/, "");
  try { JSON.parse(src); } catch { return null; }
  let out = "";
  let depth = 0;
  const newline = () => `\n${unit.repeat(depth)}`;
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (c === " " || c === "\t" || c === "\n" || c === "\r") continue;
    if (c === '"') {
      let j = i + 1;
      while (src[j] !== '"') j += src[j] === "\\" ? 2 : 1;
      out += src.slice(i, j + 1);
      i = j;
    } else if (c === "{" || c === "[") {
      let j = i + 1;
      while (/\s/.test(src[j])) j++;
      if (src[j] === (c === "{" ? "}" : "]")) { out += c + src[j]; i = j; } else { depth++; out += c + newline(); }
    } else if (c === "}" || c === "]") {
      depth--;
      out += newline() + c;
    } else if (c === ",") {
      out += "," + newline();
    } else if (c === ":") {
      out += ": ";
    } else {
      let j = i;
      while (j < src.length && !/[\s,:{}\[\]"]/.test(src[j])) j++;
      out += src.slice(i, j);
      i = j - 1;
    }
  }
  return out + "\n";
}

const lines = (text) => text.split("\n").length;
const longest = (text) => Math.max(...text.split("\n").map((line) => line.length));

// Is this a JSON file that is hard to read as it is: some line is very long, and printing it out gives many more lines and
// much shorter ones (a file with one long string in it is not made easier to read by it).
function looksMinified(text) {
  if (text.length > MAX_BYTES || longest(text) <= LONG_LINE) return false;
  const shown = pretty(text);
  return shown !== null && lines(shown) >= 2 * lines(text) && longest(shown) <= longest(text) / 2;
}

// The pretty text of a file's content, or null when it should be shown as it is.
function viewOf(text) {
  return looksMinified(text) ? pretty(text) : null;
}

module.exports = { MAX_BYTES, LONG_LINE, pretty, looksMinified, viewOf };
