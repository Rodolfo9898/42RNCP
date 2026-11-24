import type * as vscode from "vscode";
import type { SessionState } from "../session/session-state";
import type { CheckNodeBuilder } from "./check-nodes";
import type { ReviewNode } from "./review-node";
import { aiNode, groupNodes, resultNode } from "./summary-nodes";

/** The Review view: the result, and every check under the status it has. A check opens the file and line it cites. */
export class ReviewTree implements vscode.TreeDataProvider<ReviewNode> {
  readonly onDidChangeTreeData: vscode.Event<void>;

  constructor(private readonly session: SessionState, private readonly checks: CheckNodeBuilder) {
    this.onDidChangeTreeData = session.onDidChange;
  }

  getTreeItem(node: ReviewNode): vscode.TreeItem { return node.item; }

  getChildren(node?: ReviewNode): ReviewNode[] {
    const view = this.session.current;
    if (!view || !view.repo) return [];
    if (node) return node.children ? node.children() : [];
    const ai = aiNode(view.ai);
    return [resultNode(view, this.session.busy()), ...(ai ? [ai] : []), ...groupNodes(view, this.checks)];
  }
}
