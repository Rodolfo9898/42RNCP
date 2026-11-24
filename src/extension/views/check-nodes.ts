import * as vscode from "vscode";
import type { AiState, CheckResult } from "../api/types";
import type { ProjectFolder } from "../session/project-folder";
import type { ReviewNode } from "./review-node";
import { assessmentOf, shownStatus, themedIcon } from "./check-status";

const MAX_SOURCES = 4;

/** Builds the row of one check, step by step (Builder): the check itself, then what is under it, each part a small method. Everything
 * it shows comes from untrusted input (subject PDFs, repositories): it is only ever put in labels and plain text. */
export class CheckNodeBuilder {
  constructor(private readonly folder: ProjectFolder) {}

  build(result: CheckResult, ai: AiState): ReviewNode {
    const extra = [...this.assessment(result, ai), ...this.evidence(result), ...this.log(result), ...this.sources(result)];
    const item = new vscode.TreeItem(`${result.title}${result.section === "bonus" ? " [bonus]" : ""}`,
      extra.length ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None);
    item.description = result.detail || "";
    const tooltip = new vscode.MarkdownString();
    tooltip.appendText(`${result.title}\n\n${result.detail || ""}${result.by === "Claude" ? "\n\n(from claude's review)" : ""}`);
    item.tooltip = tooltip;
    item.iconPath = themedIcon(shownStatus(result, ai));
    if (extra.length === 1 && extra[0].item.command) item.command = extra[0].item.command;
    return { item, children: () => extra };
  }

  private assessment(result: CheckResult, ai: AiState): ReviewNode[] {
    const review = assessmentOf(result, ai);
    if (!review) return [];
    const item = new vscode.TreeItem(`${review.by || "AI"}: ${review.assessment.replace(/_/g, " ")}`);
    item.description = review.finding || "";
    item.tooltip = [review.finding, review.why_manual && `Check by hand: ${review.why_manual}`, "AI-generated, unverified"].filter(Boolean).join("\n\n");
    item.iconPath = new vscode.ThemeIcon("sparkle");
    return [{ item }];
  }

  private evidence(result: CheckResult): ReviewNode[] {
    return (result.evidence ?? []).map((e) => {
      const item = new vscode.TreeItem(e.line ? `${e.file}:${e.line}` : e.file);
      item.description = e.snippet || "";
      item.iconPath = new vscode.ThemeIcon("go-to-file");
      const uri = this.folder.uri(e.file);
      if (uri) {
        const line = Math.max((e.line || 1) - 1, 0);
        item.command = { command: "vscode.open", title: "Open", arguments: [uri, { selection: new vscode.Range(line, 0, line, 0) }] };
      }
      return { item };
    });
  }

  private log(result: CheckResult): ReviewNode[] {
    if (!result.log) return [];
    const item = new vscode.TreeItem("Show the log");
    item.iconPath = new vscode.ThemeIcon("output");
    item.command = { command: "verdict.showText", title: "Show the log", arguments: [result.log, "log"] };
    return [{ item }];
  }

  private sources(result: CheckResult): ReviewNode[] {
    return (result.sources ?? []).slice(0, MAX_SOURCES).map((source) => {
      const item = new vscode.TreeItem(`From ${source.pdf}${source.page ? `, page ${source.page}` : ""}`);
      item.iconPath = new vscode.ThemeIcon("file-pdf");
      item.command = { command: "verdict.openSubject", title: "Open the PDF", arguments: [source.pdf, source.page] };
      return { item };
    });
  }
}
