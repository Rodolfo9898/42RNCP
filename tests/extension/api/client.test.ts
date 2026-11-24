import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient, ApiError } from "../../../src/extension/api/client";

const reply = (body: unknown, status = 200, statusText = ""): Response => new Response(body === null ? null : JSON.stringify(body), { status, statusText });

function client(answer: (url: string, init: RequestInit) => Response | Promise<Response>): { api: ApiClient; sent: Array<{ url: string; init: RequestInit }> } {
  const sent: Array<{ url: string; init: RequestInit }> = [];
  const api = new ApiClient("http://web:8000", async (input, init = {}) => { sent.push({ url: String(input), init }); return answer(String(input), init); });
  return { api, sent };
}

test("a JSON route is asked under /api/ with the method and the body given, and its answer is parsed", async () => {
  const { api, sent } = client(() => reply({ id: "s1" }));
  assert.deepEqual(await api.json("sessions/s1"), { id: "s1" });
  assert.deepEqual(await api.json("sessions/s1/subjects", { method: "POST", body: { paths: ["a.pdf"] } }), { id: "s1" });
  assert.equal(sent[0].url, "http://web:8000/api/sessions/s1");
  assert.equal(sent[0].init.method, "GET");
  assert.equal(sent[1].init.method, "POST");
  assert.equal(sent[1].init.body, '{"paths":["a.pdf"]}');
  assert.deepEqual(sent[1].init.headers, { "content-type": "application/json" });
});

test("a form is sent as it is, without a JSON content type that would break its boundary", async () => {
  const { api, sent } = client(() => reply({ items: [] }, 201));
  const form = new FormData();
  form.append("files", new Blob(["%PDF"]), "a.pdf");
  await api.json("library/common-core/subjects", { method: "POST", form });
  assert.equal(sent[0].init.body, form);
  assert.deepEqual(sent[0].init.headers, {});
});

test("an answer without a body is null, and a body that is not JSON is the text", async () => {
  assert.equal(await client(() => reply(null, 204)).api.json("sessions/s1", { method: "DELETE" }), null);
  assert.equal(await client(() => new Response("plain words")).api.json("x"), "plain words");
});

test("a refusal carries the status and the app's own explanation", async () => {
  const { api } = client(() => reply({ detail: "run the checks first" }, 400));
  await assert.rejects(api.json("sessions/s1/claude-review", { method: "PUT", body: { force: true } }), (err: ApiError) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.message, "run the checks first");
    assert.equal(err.status, 400);
    return true;
  });
  await assert.rejects(client(() => reply({ detail: [{ msg: "x" }] }, 422, "Unprocessable")).api.json("x"), { message: "422 Unprocessable", status: 422 });
  await assert.rejects(client(() => new Response("boom", { status: 502 })).api.json("x"), { message: "boom", status: 502 });                  // (a proxy's plain text)
  await assert.rejects(client(() => new Response(null, { status: 502, statusText: "Bad Gateway" })).api.json("x"), { message: "502 Bad Gateway", status: 502 });
});

test("a service that cannot be reached is said so, without a status", async () => {
  const { api } = client(() => { throw new Error("connect ECONNREFUSED"); });
  await assert.rejects(api.json("health"), (err: ApiError) => {
    assert.match(err.message, /^the Verdict service \(http:\/\/web:8000\) cannot be reached: connect ECONNREFUSED$/);
    assert.equal(err.status, undefined);
    return true;
  });
  await assert.rejects(api.bytes("x"), /cannot be reached/);
});

test("a binary answer comes back as bytes, and a text answer as text; both refuse an error status", async () => {
  const { api } = client((url) => (url.endsWith("missing") ? new Response("no", { status: 404, statusText: "Not Found" }) : new Response(Buffer.from("png-bytes"))));
  assert.equal((await api.bytes("pages/1.png")).toString(), "png-bytes");
  assert.equal(await api.text("verdict.md"), "png-bytes");
  await assert.rejects(api.bytes("missing"), { message: "404 Not Found", status: 404 });
  await assert.rejects(api.text("missing"), { message: "404 Not Found", status: 404 });
});
