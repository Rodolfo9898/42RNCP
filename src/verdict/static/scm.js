"use strict";

// Source Control: what changed in the project since its last commit, and the diff editor. It is read-only (nothing here stages or commits;
// that is done in a terminal). The server reads git with the repository's own settings switched off, so a hostile repository runs nothing.
// The same diff editor compares two files of the explorer.

const scm = { data: null, error: "", loading: false, again: false, at: 0, timer: null, collapsed: new Set(), spec: null };

const scmCount = () => (scm.data && scm.data.available ? scm.data.files.length : 0);

registerContainer({ id: "scm", title: "Source Control", icon: "branch", location: "sidebar", order: 3, badge: scmCount });

async function loadScm({ force = false } = {}) {
  if (!sid || !session?.repo) { scm.data = null; scm.error = ""; bus.emit("scm"); return; }
  if (scm.loading) { scm.again = true; return; }
  if (!force && Date.now() - scm.at < 1500) { scheduleScm(1500); return; }
  scm.loading = true;
  try {
    scm.data = await api(`sessions/${sid}/git/status`);
    scm.error = "";
  } catch (err) {
    scm.data = null;
    scm.error = err.message;
  } finally {
    scm.loading = false;
    scm.at = Date.now();
    bus.emit("scm");
    if (scm.again) { scm.again = false; scheduleScm(); }
  }
}

function scheduleScm(delay = 700) {
  clearTimeout(scm.timer);
  scm.timer = setTimeout(() => loadScm(), delay);
}

const changeOf = (path) => (scm.data?.available ? scm.data.files.find((f) => f.path === path) : null);

bus.on("tree", () => scheduleScm());
bus.on("scm", () => {
  decorateTree();
  if (!layout) return;
  if (viewIsVisible("scm")) viewSpecs.get("scm").refresh();
  renderActivityBar();
});
window.addEventListener("focus", () => { if (session?.repo) scheduleScm(300); });

// ------------------------------------------------------------------ the view

registerView({
  id: "scm", container: "scm", title: "Source Control",
  create(body) {
    this.head = h("div", { class: "scm-head" });
    this.list = h("div", { class: "scm-list", role: "tree" });
    body.append(h("div", { class: "scm-view" }, this.head, this.list));
    scm.spec = this;
    loadScm({ force: true });
  },
  refresh() { renderScm(this); },
  actions: () => [
    { icon: "refresh", title: "Refresh", run: () => loadScm({ force: true }) },
    { icon: "collapse-all", title: "Collapse All", run: () => { for (const g of scmGroups(scm.data?.files ?? [])) scm.collapsed.add(g.id); renderScm(scm.spec); }, hidden: !scmCount() },
  ],
});

function renderScm(spec) {
  if (!spec?.list) return;
  const { head, list } = spec;
  const note = (text, extra = null) => list.replaceChildren(h("div", { class: "scm-note" }, h("p", {}, text), extra));
  if (!session?.repo) {
    head.replaceChildren();
    return note("There is no project open, so there is nothing to track.", h("button", { class: "primary wide", onclick: () => runCommand("workbench.action.files.openProject") }, "Open Project…"));
  }
  const d = scm.data;
  if (scm.error) { head.replaceChildren(); return note(scm.error); }
  if (!d) { head.replaceChildren(); return note("Looking at what changed…"); }
  if (!d.available) { head.replaceChildren(); return note(d.error || "Git is not available for this folder."); }

  const branch = d.branch && d.branch !== "(detached)" ? d.branch : `(${d.head || "detached"})`;
  head.replaceChildren(
    h("span", { class: "scm-branch", title: d.upstream ? `${branch} tracks ${d.upstream}` : `${branch} has no upstream branch` }, icon("branch", 14), h("span", {}, branch)),
    d.ahead || d.behind ? h("span", { class: "scm-sync", title: `${d.ahead} commit(s) to push, ${d.behind} to pull` }, `${d.ahead}↑ ${d.behind}↓`) : null,
    d.head ? h("span", { class: "scm-commit" }, d.head) : null,
    h("span", { class: "spacer" }),
    h("span", { class: "scm-readonly", title: "This view shows what changed. Stage and commit in a terminal." }, "read-only"));

  const groups = scmGroups(d.files);
  if (!groups.length) return note("No changes: the project is exactly as it was committed.");
  list.replaceChildren(...groups.flatMap((g) => {
    const closed = scm.collapsed.has(g.id);
    const title = h("div", {
      class: "row scm-group", role: "treeitem", "aria-expanded": String(!closed), "data-group": g.id,
      onclick: () => { closed ? scm.collapsed.delete(g.id) : scm.collapsed.add(g.id); renderScm(spec); },
    }, h("span", { class: "twisty" }, icon(closed ? "chevron-right" : "chevron-down", 14)), h("span", { class: "row-name" }, g.title), h("span", { class: "count" }, String(g.entries.length)));
    return [title, ...(closed ? [] : g.entries.map(scmRow))];
  }));
  if (d.truncated) list.append(h("p", { class: "hint" }, "Only the first changes are listed."));
}

function scmRow(entry) {
  const name = entry.path.split("/").pop();
  const dir = entry.path.includes("/") ? entry.path.slice(0, entry.path.lastIndexOf("/")) : "";
  const label = `${SCM_KIND_TITLES[entry.kind] ?? entry.kind}${entry.from ? `, renamed from ${entry.from}` : ""}`;
  return h("div", {
    class: `row scm-row scm-${entry.kind}`, role: "treeitem", "data-path": entry.path, "data-staged": String(entry.staged), title: `${entry.path} • ${label}`,
    onclick: () => guarded(() => openDiff(entry.path, { staged: entry.staged, old: entry.from, preview: true })),
    ondblclick: () => guarded(() => openDiff(entry.path, { staged: entry.staged, old: entry.from, preview: false })),
    oncontextmenu: (ev) => showContextMenu(ev, scmMenu(entry)),
  }, fileIcon(iconFor(name)), h("span", { class: "row-name" }, name), h("span", { class: "row-dir" }, entry.from ? `${entry.from} → ${dir || "."}` : dir),
  h("span", { class: `scm-status scm-${entry.kind}`, title: label }, entry.letter));
}

function scmMenu(entry) {
  return [
    { label: "Open Changes", run: () => guarded(() => openDiff(entry.path, { staged: entry.staged, old: entry.from, preview: false })) },
    { label: "Open File", disabled: entry.kind === "deleted", run: () => guarded(() => openFile(entry.path)) },
    "-",
    { label: "Copy Path", run: () => copyText(entry.path, "the path") },
    { label: "Reveal in Explorer", disabled: entry.kind === "deleted", run: () => runCommand("workbench.files.revealInExplorer", entry.path) },
  ];
}

// The explorer shows a letter after a file that changed, in the colour of its change, and a dot after the folders that hold one.
function decorateTree() {
  const root = $("#tree");
  if (!root) return;
  for (const old of $$(".git-badge, .git-dot", root)) old.remove();
  for (const row of $$(".row.git-changed", root)) row.classList.remove("git-changed", "scm-modified", "scm-added", "scm-deleted", "scm-renamed", "scm-untracked", "scm-conflict");
  if (!scm.data?.available) return;
  const { byPath, folders } = scmDecorations(scm.data.files);
  for (const row of $$(".row[data-path]", root)) {
    const mark = byPath[row.dataset.path];
    if (!mark) continue;
    row.classList.add("git-changed", `scm-${mark.kind}`);
    row.append(h("span", { class: `git-badge scm-${mark.kind}`, title: SCM_KIND_TITLES[mark.kind] }, mark.letter));
  }
  const open = new Set(folders);
  for (const row of $$(".row[data-dir]", root)) {
    if (open.has(row.dataset.dir)) row.append(h("span", { class: "git-dot", title: "Contains changes" }, "●"));
  }
}

// ------------------------------------------------------------------ the diff editor

async function openDiff(path, { staged = false, old = null, preview = false } = {}) {
  const key = `diff:${staged ? "index" : "tree"}:${path}`;
  if (tabs.has(key)) { if (!preview) pinTab(key); showTab(key); return tabs.get(key); }
  const params = new URLSearchParams({ path, staged: String(staged) });
  if (old) params.set("old", old);
  const answer = await api(`sessions/${sid}/git/diff?${params}`);
  if (tabs.has(key)) { showTab(key); return tabs.get(key); }
  const name = path.split("/").pop();
  return showDiff(key, `${name} (${staged ? "Index" : "Working Tree"})`, {
    before: answer.before, after: answer.after, binary: answer.binary, truncated: answer.truncated, state: answer.state,
    leftTitle: `${old || path} (${staged ? "HEAD" : "Index"})`, rightTitle: `${path} (${staged ? "Index" : "Working Tree"})`, path, preview,
  });
}

// Two files of the explorer against each other (Select for Compare, then Compare with Selected).
async function compareFiles(a, b) {
  const [left, right] = await Promise.all([a, b].map((p) => api(`sessions/${sid}/file?path=${encodeURIComponent(p)}`)));
  const key = `compare:${a}|${b}`;
  if (tabs.has(key)) return showTab(key);
  const name = (p) => p.split("/").pop();
  return showDiff(key, `${name(a)} ↔ ${name(b)}`, {
    before: left.content ?? "", after: right.content ?? "", binary: !!(left.binary || right.binary), truncated: !!(left.truncated || right.truncated), state: "modified",
    leftTitle: a, rightTitle: b, path: null, preview: false,
  });
}

function showDiff(key, title, spec) {
  const diff = buildDiff(spec);
  const target = editors.active;
  if (spec.preview) closePreviews(target);
  addTab(key, title, diff.view, true, { group: target });
  const tab = tabs.get(key);
  Object.assign(tab, {
    kind: "diff", preview: !!spec.preview, tooltip: `${spec.leftTitle} ↔ ${spec.rightTitle}`, diff, language: "diff", iconEl: () => icon("git-diff", 14),
    actions: () => [
      { icon: "arrow-up", title: `Previous Change (${keyLabel("workbench.action.compareEditor.previousChange")})`, run: () => diff.step(-1), disabled: !diff.hunkCount() },
      { icon: "arrow-down", title: `Next Change (${keyLabel("workbench.action.compareEditor.nextChange")})`, run: () => diff.step(1), disabled: !diff.hunkCount() },
      { icon: diff.inline ? "split-right" : "list", title: diff.inline ? "Switch to Side by Side View" : "Switch to Inline View", run: () => { diff.setInline(!diff.inline); renderEditors(); } },
      ...(spec.path && spec.state !== "deleted" ? [{ icon: "file", title: "Open File", run: () => guarded(() => openFile(spec.path)) }] : []),
    ],
  });
  showTab(key);
  return tab;
}

// Builds the view: side by side by default, two columns that scroll together vertically and each sideways by itself.
function buildDiff({ before, after, binary, truncated, leftTitle, rightTitle }) {
  const view = h("div", { class: "view diff-view", tabindex: "-1" });
  const model = { inline: false, open: new Set(), current: -1, rows: [], rowEls: [] };
  if (binary) {
    view.append(h("div", { class: "notice" }, "The files differ, but they are binary: there is no text to compare."));
    return { view, inline: false, hunkCount: () => 0, step() {}, setInline() {} };
  }
  const lines = (text) => (text === "" ? [] : text.replace(/\n$/, "").split("\n"));
  model.rows = diffRows(lines(before), lines(after));
  const hunks = diffHunks(model.rows);
  const position = h("span", { class: "diff-position" });
  const header = h("div", { class: "diff-titles" }, h("div", {}, leftTitle), h("div", {}, rightTitle, position));
  const body = h("div", { class: "diff-body" });
  const notice = truncated ? h("div", { class: "notice" }, "Long files are cut: only the first megabyte of each is compared.") : null;
  appendNodes(view, header, notice, body);

  const draw = () => {
    const segments = diffFold(model.rows, 3, [...model.open]);
    model.rowEls = [];
    const num = (side) => h("span", { class: "diff-num" }, side ? String(side.n) : "");
    const text = (side) => h("span", { class: "diff-text" }, side ? side.text : "");
    const line = (cls, ...kids) => h("div", { class: `diff-line ${cls}` }, ...kids);
    const foldRow = (seg) => h("button", { class: "diff-fold", title: "Show the unchanged lines", onclick: () => { model.open.add(seg.from); draw(); } },
      icon("chevron-right", 12), `${seg.to - seg.from} unchanged line${seg.to - seg.from === 1 ? "" : "s"}`);
    if (!model.rows.some((r) => r.kind !== "eq")) {
      body.replaceChildren(h("div", { class: "notice" }, "The files are identical."));
      return;
    }
    if (model.inline) {
      const column = h("div", { class: "diff-side diff-inline" });
      for (const seg of segments) {
        if (seg.kind === "fold") { column.append(foldRow(seg)); continue; }
        for (let i = seg.from; i < seg.to; i++) {
          const r = model.rows[i];
          const els = [];
          if (r.kind === "eq") els.push(line("eq", num(r.left), num(r.right), text(r.right)));
          else {
            if (r.left) els.push(line("removed", num(r.left), num(null), text(r.left)));
            if (r.right) els.push(line("added", num(null), num(r.right), text(r.right)));
          }
          model.rowEls[i] = els;
          column.append(...els);
        }
      }
      body.replaceChildren(column);
    } else {
      const left = h("div", { class: "diff-side diff-left", "aria-label": leftTitle }), right = h("div", { class: "diff-side diff-right", "aria-label": rightTitle });
      for (const seg of segments) {
        if (seg.kind === "fold") { left.append(foldRow(seg)); right.append(foldRow(seg)); continue; }
        for (let i = seg.from; i < seg.to; i++) {
          const r = model.rows[i];
          const l = line(r.kind === "eq" ? "eq" : r.left ? "removed" : "filler", num(r.left), text(r.left));
          const rr = line(r.kind === "eq" ? "eq" : r.right ? "added" : "filler", num(r.right), text(r.right));
          model.rowEls[i] = [l, rr];
          left.append(l);
          right.append(rr);
        }
      }
      body.replaceChildren(left, right);
    }
    mark();
  };
  const mark = () => {
    for (const el of $$(".current-change", view)) el.classList.remove("current-change");
    if (model.current < 0) return;
    const start = hunks[model.current];
    for (let i = start; i < model.rows.length && (i === start || model.rows[i].kind !== "eq"); i++) for (const el of model.rowEls[i] ?? []) el.classList.add("current-change");
  };
  draw();

  return {
    view,
    get inline() { return model.inline; },
    hunkCount: () => hunks.length,
    setInline(on) { model.inline = on; draw(); },
    step(by) {
      if (!hunks.length) return;
      model.current = (model.current + by + hunks.length) % hunks.length;
      const row = hunks[model.current];
      const folded = diffFold(model.rows, 3, [...model.open]).find((s) => s.kind === "fold" && row >= s.from && row < s.to);
      if (folded) { model.open.add(folded.from); draw(); } else mark();
      model.rowEls[row]?.[0]?.scrollIntoView?.({ block: "center" });
      position.textContent = `Difference ${model.current + 1} of ${hunks.length}`;
    },
  };
}
