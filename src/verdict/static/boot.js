"use strict";

// Starts the page once every script has been read, and wires what belongs to the page as a whole: the settings that change how it looks,
// the keys of the dialog, and PDFs dropped on the window.

// ------------------------------------------------------------------ settings that change the look of the page

function repaintEditorOverlays() {
  // (the boxes behind the text were placed with the line height of the moment: place them again)
  for (const tab of tabs.values()) if (tab.codeEl) for (const el of $$(".hl, .current-line", tab.codeEl)) el.remove();
  if (typeof runFind === "function" && find.widget && !find.widget.hidden) runFind(false);
  bus.emit("fit");
}

bus.on("setting", (id) => {
  if (id === "workbench.colorTheme") applyTheme();
  if (id.startsWith("editor.") || id === "window.zoomLevel") {
    applyEditorSettings();
    if (id === "editor.bracketPairColorization.enabled") rebuildSources();
    repaintEditorOverlays();
  }
  if (id.startsWith("editor.") || id.startsWith("breadcrumbs.") || id === "workbench.editor.showTabs") renderEditors();
  refreshStatusBar();
});

bus.on("dialog", (open) => setContext("dialogVisible", open));
bus.on("tab:active", () => refreshTitle());
bus.on("layout", () => {
  setContext("zenMode", !!layout?.zen);
  refreshTitle();
});
bus.on("terminals", () => setContext("terminalIsOpen", termPanes(terminals).length > 0));

$("#modal").addEventListener("click", (ev) => { if (ev.target.id === "modal") closeDialog(); });
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && dialogOpen()) closeDialog(); });
$("#file-input").addEventListener("change", (ev) => {
  const pdfs = pdfsOf(ev.target.files);
  guarded(() => uploadFiles(pdfs, pendingTrack));
  ev.target.value = "";
});

// ------------------------------------------------------------------ PDFs dropped anywhere on the window are subject uploads

let filesOver = 0;
const carriesFiles = (ev) => [...(ev.dataTransfer?.types ?? [])].includes("Files");
const endFileDrag = () => { filesOver = 0; document.body.classList.remove("dragging-files"); };

document.addEventListener("dragenter", (ev) => { if (carriesFiles(ev)) { filesOver += 1; document.body.classList.add("dragging-files"); } });
document.addEventListener("dragover", (ev) => { if (carriesFiles(ev)) { ev.preventDefault(); ev.dataTransfer.dropEffect = "copy"; } });
document.addEventListener("dragleave", (ev) => { if (carriesFiles(ev) && (filesOver -= 1) <= 0) endFileDrag(); });
document.addEventListener("drop", (ev) => {
  if (!carriesFiles(ev)) return;
  ev.preventDefault();
  endFileDrag();
  guarded(() => openUpload(ev.dataTransfer.files));
});

// ------------------------------------------------------------------ go

const appReady = init().catch((err) => {
  notify(err.message, { level: "error" });
  if (!layout) { try { initLayout(); buildStatusBar(); } catch (inner) { console.error(inner); } }           // (something to look at, and the menus, even without a server)
});
window.verdictReady = appReady;
