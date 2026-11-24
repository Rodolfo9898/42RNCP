import assert from "node:assert/strict";
import test from "node:test";
import { pageHtml } from "../../../../src/extension/viewers/pdf/pdf-page";

test("the page can only show the images it is given: no network, nothing inline without the nonce", () => {
  const html = pageHtml("abc123", { name: "push_swap.pdf", pages: 12, page: 1 });
  const csp = (html.match(/Content-Security-Policy" content="([^"]+)"/) as RegExpMatchArray)[1];
  assert.match(csp, /default-src 'none'/);
  assert.match(csp, /img-src data:;/);
  assert.ok(!/https?:|unsafe-inline|unsafe-eval|connect-src/.test(csp), csp);
  assert.match(csp, /script-src 'nonce-abc123'/);
  assert.match(csp, /style-src 'nonce-abc123'/);
  assert.equal([...html.matchAll(/<(script|style) nonce="([0-9a-z]+)"/g)].every((m) => m[2] === "abc123"), true);
});

test("the page is told the name, the number of pages and the page to show first", () => {
  const html = pageHtml("n", { name: "push_swap.pdf", pages: 12, page: 5 });
  assert.match(html, /const CONFIG = \{"name":"push_swap.pdf","pages":12,"page":5\}/);
});

test("a file name cannot break out of the page's script", () => {
  const html = pageHtml("n", { name: "</script><b>.pdf", pages: 1, page: 1 });
  assert.ok(html.includes("\\u003c/script>"));
  assert.equal(html.match(/<\/script>/g)?.length, 2, "only the two script tags of the page itself");
  assert.ok(!html.includes("<b>"));
});
