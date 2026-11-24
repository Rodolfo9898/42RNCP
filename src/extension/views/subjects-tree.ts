import * as vscode from "vscode";
import type { Subject } from "../api/types";
import type { SessionState } from "../session/session-state";

/** A row of the Subjects view; `subject` is the PDF's name, which the commands of the row ask for. */
export class SubjectItem extends vscode.TreeItem {
  constructor(readonly subject: string, label: string) { super(label); }
}

function subjectItem(s: Subject): SubjectItem {
  const norm = s.kind === "norm";
  const item = new SubjectItem(s.name, s.name);
  item.description = norm ? "the Norm (C code was found)" : [s.track, `${s.rules.length} rules`, s.lang && s.lang.toUpperCase()].filter(Boolean).join(" · ");
  item.tooltip = s.rules.map((r) => `${r.kind === "manual" ? "?" : "⚙"} ${r.title}`).join("\n");
  item.iconPath = new vscode.ThemeIcon(norm ? "law" : "file-pdf");
  item.contextValue = norm ? "norm" : "subject";
  item.command = { command: "verdict.openSubject", title: "Open the PDF", arguments: [s.name] };
  return item;
}

/** The Subjects view: the PDFs of the review (and the Norm, once C code was found). */
export class SubjectsTree implements vscode.TreeDataProvider<SubjectItem> {
  readonly onDidChangeTreeData: vscode.Event<void>;

  constructor(private readonly session: SessionState) {
    this.onDidChangeTreeData = session.onDidChange;
  }

  getTreeItem(node: SubjectItem): vscode.TreeItem { return node; }

  getChildren(node?: SubjectItem): SubjectItem[] {
    const view = this.session.current;
    return node || !view ? [] : view.subjects.map(subjectItem);
  }
}
