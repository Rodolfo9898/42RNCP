import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../../../src/extension/api/client";
import { VerdictApi } from "../../../src/extension/api/verdict-api";
import { FakeApp } from "../support/fake-app";
import { aMerge, aSession } from "../support/fixtures";

// The routes of the REST API ("Public REST API" of the app): what the extension asks for, method, path and body.

function talk(): { api: VerdictApi; app: FakeApp } {
  const app = new FakeApp();
  return { api: new VerdictApi(new ApiClient("http://web:8000", app.fetch as typeof fetch)), app };
}

const sent = (app: FakeApp): string[] => app.requests.map((r) => `${r.method} ${r.route}`);

test("the session routes: create, read, add subjects, remove one, run, AI review", async () => {
  const { api, app } = talk();
  for (const key of ["POST sessions", "GET sessions/s1", "POST sessions/s1/subjects", "DELETE sessions/s1/subjects/a%20b.pdf", "POST sessions/s1/runs",
    "POST sessions/s1/ai-review"]) app.on(key, aSession());
  await api.createSession();
  await api.session("s1");
  await api.addSubjects("s1", ["common-core/libft.pdf"]);
  await api.removeSubject("s1", "a b.pdf");
  await api.startRun("s1");
  await api.startAiReview("s1");
  assert.deepEqual(sent(app), ["POST sessions", "GET sessions/s1", "POST sessions/s1/subjects", "DELETE sessions/s1/subjects/a%20b.pdf", "POST sessions/s1/runs",
    "POST sessions/s1/ai-review"]);
  assert.deepEqual(app.calls("POST sessions/s1/subjects")[0].body, { paths: ["common-core/libft.pdf"] });
});

test("the repository is chosen with one route and a kind: clone or existing", async () => {
  const { api, app } = talk();
  app.on("PUT sessions/s1/repo", aSession());
  await api.cloneRepo("s1", { url: "git@host:me/x.git", name: "x", destination: "rncp" });
  await api.useExistingRepo("s1", "rncp/x");
  assert.deepEqual(app.requests.map((r) => r.body), [
    { kind: "clone", url: "git@host:me/x.git", name: "x", destination: "rncp" },
    { kind: "existing", path: "rncp/x" },
  ]);
});

test("uploaded PDFs go into the library of a track (the files only, the track is in the path) and the answer says where they went", async () => {
  const { api, app } = talk();
  app.on("POST library/common-core/subjects", { items: [{ path: "common-core/a.pdf", name: "a.pdf", track: "common-core", size: 4 }] }, 201);
  const items = await api.uploadSubjects("common-core", [{ name: "a.pdf", bytes: Buffer.from("%PDF") }, { name: "b.pdf", bytes: Buffer.from("%PDF") }]);
  assert.deepEqual(items.map((i) => i.path), ["common-core/a.pdf"]);
  const form = app.requests[0].form as FormData;
  assert.deepEqual([...form.keys()], ["files", "files"]);
  assert.deepEqual(form.getAll("files").map((f) => (f as File).name), ["a.pdf", "b.pdf"]);
  assert.equal((form.getAll("files")[0] as File).type, "application/pdf");
});

test("claude's report: one route, PUT, forced or not, and the answer has the same fields either way", async () => {
  const { api, app } = talk();
  app.on("PUT sessions/s1/claude-review", aMerge());
  const automatic = await api.claudeReview("s1", false);
  const forced = await api.claudeReview("s1", true);
  assert.deepEqual(app.requests.map((r) => r.body), [{ force: false }, { force: true }]);
  assert.deepEqual(Object.keys(automatic).sort(), Object.keys(forced).sort());
});

test("prompts, Progress.md, the verdict and the page images", async () => {
  const { api, app } = talk();
  app.on("GET sessions/s1/prompts/review", { text: "r" }).on("GET sessions/s1/prompts/fix", { text: "f", must_fix: 1, look_at: 2 })
    .on("PUT sessions/s1/progress", { project: "x", result: "PASS", symbol: "✅", before: null, changed: true })
    .on("GET sessions/s1/subjects/a%20b.pdf/pages/3.png", Buffer.from("png"));
  assert.equal((await api.reviewPrompt("s1")).text, "r");
  assert.equal((await api.fixPrompt("s1")).must_fix, 1);
  assert.equal((await api.updateProgress("s1")).changed, true);
  assert.equal((await api.pagePng("s1", "a b.pdf", 3)).toString(), "png");
  assert.deepEqual(sent(app), ["GET sessions/s1/prompts/review", "GET sessions/s1/prompts/fix", "PUT sessions/s1/progress", "GET sessions/s1/subjects/a%20b.pdf/pages/3.png"]);
});

test("health, the environment (quick or deep), the library, and the projects with where a clone can go", async () => {
  const { api, app } = talk();
  app.on("GET health", { llm: {} }).on("GET environment", { ready: true }).on("GET environment?deep=true", { ready: true })
    .on("GET library", { tracks: [], items: [] }).on("GET projects", { root: "projects", folders: ["rncp"], existing: [{ path: "rncp/x", git: true }] });
  await api.health();
  await api.environment(false);
  await api.environment(true);
  await api.library();
  assert.deepEqual((await api.projects()).existing, [{ path: "rncp/x", git: true }]);
  assert.deepEqual(sent(app), ["GET health", "GET environment", "GET environment?deep=true", "GET library", "GET projects"]);
});
