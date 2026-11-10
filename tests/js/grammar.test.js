"use strict";

// The colours of .gitignore / .dockerignore files (terminal/vscode/verdict/syntaxes/ignore.tmLanguage.json), tokenized by VS Code's own
// engine (vscode-textmate + oniguruma). Needs `npm install` in this folder (make test-extension); skipped without it.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");

let textmate = null;
let onig = null;
try {
  textmate = require("vscode-textmate");
  onig = require("vscode-oniguruma");
} catch { /* not installed */ }

const GRAMMAR = path.resolve(__dirname, "../../terminal/vscode/verdict/syntaxes/ignore.tmLanguage.json");
const SCOPE = "source.verdict-ignore";

async function tokenize(text) {
  const wasm = fs.readFileSync(require.resolve("vscode-oniguruma/release/onig.wasm")).buffer;
  await onig.loadWASM(wasm);
  const registry = new textmate.Registry({
    onigLib: Promise.resolve({ createOnigScanner: (p) => new onig.OnigScanner(p), createOnigString: (s) => new onig.OnigString(s) }),
    loadGrammar: async (scope) => (scope === SCOPE ? textmate.parseRawGrammar(fs.readFileSync(GRAMMAR, "utf8"), GRAMMAR) : null),
  });
  const grammar = await registry.loadGrammar(SCOPE);
  let stack = textmate.INITIAL;
  return text.split("\n").map((line) => {
    const result = grammar.tokenizeLine(line, stack);
    stack = result.ruleStack;
    return result.tokens.map((t) => [line.slice(t.startIndex, t.endIndex), t.scopes.slice(1).map((s) => s.replace(/\.verdict-ignore$/, ""))]);
  });
}

const skip = textmate ? false : "vscode-textmate is not installed (make test-extension)";
const last = (tokens, text) => tokens.find(([t]) => t === text)?.[1].at(-1);

test("comments are comments only at the start of a line", { skip }, async () => {
  const [comment, indented, trailing] = await tokenize("# build output\n  # not one: git reads it as a pattern\n.env # nor this");
  assert.deepEqual(comment, [["# build output", ["comment.line.number-sign"]]]);
  assert.equal(indented[0][1].at(-1), "string.unquoted.pattern");
  assert.equal(trailing[0][1].at(-1), "string.unquoted.pattern");
});

test("a pattern has its negation, wildcards, character classes, escapes and slashes coloured", { skip }, async () => {
  const [negated, glob, rooted, deep, klass, escaped] = await tokenize("!keep.o\n*.o\n/build/\n**/node_modules/\nfoo[0-9]?.txt\n\\#file");
  assert.equal(last(negated, "!"), "keyword.control.negation");
  assert.equal(last(negated, "keep.o"), "string.unquoted.pattern");
  assert.equal(last(glob, "*"), "constant.character.escape.wildcard");
  assert.equal(last(rooted, "/"), "punctuation.separator.path");
  assert.equal(last(deep, "**"), "constant.character.escape.wildcard");
  assert.equal(last(klass, "[0-9]"), "string.regexp.character-class");
  assert.equal(last(klass, "?"), "constant.character.escape.wildcard");
  assert.equal(last(escaped, "\\#"), "constant.character.escape");
});

test("blank lines do not break the lines after them", { skip }, async () => {
  const lines = await tokenize("a\n\n   \nb c\n!d\n# end");
  assert.equal(lines[3][0][1].at(-1), "string.unquoted.pattern");
  assert.equal(last(lines[4], "!"), "keyword.control.negation");
  assert.equal(lines[5][0][1].at(-1), "comment.line.number-sign");
});
