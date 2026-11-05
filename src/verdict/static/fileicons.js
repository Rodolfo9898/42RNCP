"use strict";

// File and folder icons: VS Code Great Icons (vendor/great-icons, MIT), resolved the way VS Code resolves an icon theme:
// exact file name, then the longest matching extension, then a few types the theme only knows by language.
const ICON_BASE = "vendor/great-icons/";
const ICON_LANGUAGE = { tpp: "cpp", ipp: "cpp", hh: "cpp", hxx: "cpp" };
let iconTheme;   // undefined: not loaded yet; null: unavailable (rows simply have no icon)

async function loadIconTheme() {
  if (iconTheme !== undefined) return;
  try { iconTheme = await (await fetch(`${ICON_BASE}icons.json`)).json(); } catch { iconTheme = null; }
}

function iconFor(name, type = "file", open = false) {
  const t = iconTheme;
  if (!t) return null;
  const lower = name.toLowerCase();
  let id;
  if (type === "dir") {
    id = (open ? t.folderNamesExpanded : t.folderNames)?.[lower] ?? (open ? t.folderExpanded : t.folder);
  } else {
    id = t.fileNames?.[lower];
    const parts = lower.split(".");
    for (let i = 1; !id && i < parts.length; i++) id = t.fileExtensions?.[parts.slice(i).join(".")];
    if (!id && ICON_LANGUAGE[parts.at(-1)]) id = t.languageIds?.[ICON_LANGUAGE[parts.at(-1)]];
    id ??= t.file;
  }
  const path = t.iconDefinitions?.[id]?.iconPath;
  return path ? ICON_BASE + path.replace(/^\.\//, "") : null;
}

const fileIcon = (src) => src ? h("img", { class: "ficon", src, alt: "" }) : h("span", { class: "ficon" });
