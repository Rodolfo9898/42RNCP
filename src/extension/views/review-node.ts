import type * as vscode from "vscode";

/** One row of the Review view: what is shown, and the rows under it (made when the row is opened). */
export interface ReviewNode {
  item: vscode.TreeItem;
  children?: () => ReviewNode[];
}
