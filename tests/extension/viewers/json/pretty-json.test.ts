import assert from "node:assert/strict";
import test from "node:test";
import { looksMinified, pretty } from "../../../../src/extension/viewers/json/pretty-json";

test("pretty-printing keeps every number, string and key exactly as the file has them", () => {
  const text = '{"b":[1,2,{"x":null,"e":[]}],"big":12345678901234567890,"a":1.50e+3,"s":"a,}\\"b","o":{},"b":true}';
  assert.equal(pretty(text), [
    "{", '  "b": [', "    1,", "    2,", "    {", '      "x": null,', '      "e": []', "    }", "  ],",
    '  "big": 12345678901234567890,', '  "a": 1.50e+3,', '  "s": "a,}\\"b",', '  "o": {},', '  "b": true', "}", ""].join("\n"));
  assert.equal(pretty("\uFEFF[1]"), "[\n  1\n]\n");
  assert.equal(pretty(" 42 "), "42\n");
});

test("the indentation unit can be chosen", () => {
  assert.equal(pretty('{"a":[1]}', "\t"), '{\n\t"a": [\n\t\t1\n\t]\n}\n');
});

test("what is not JSON is not pretty-printed", () => {
  for (const text of ["", "nope", '{"a":1,}', '{"a" 1}', "[1] [2]", '{"a":1}\n{"a":2}\n', "// comment\n{}", "[1,2"]) assert.equal(pretty(text), null, text);
});

test("only a file that is hard to read, and gets easier, is shown pretty", () => {
  const wide = JSON.stringify({ levels: Array.from({ length: 40 }, (_, i) => ({ id: i, name: `level ${i}` })) });
  assert.ok(looksMinified(wide), "one long line of data");
  assert.ok(!looksMinified(JSON.stringify({ a: 1 })), "short");
  assert.ok(!looksMinified(JSON.stringify(JSON.parse(wide), null, 2)), "already pretty");
  assert.ok(!looksMinified(JSON.stringify({ text: "x".repeat(400) })), "one long string: printing it out does not help");
  assert.ok(!looksMinified(`${wide.slice(0, -2)}, oops`), "not JSON");
  assert.ok((pretty(wide) as string).split("\n").length > 100);
});
