// A subject PDF opened in the editor: the pages of the PDF as images, one under the other, scrolled like any document.
//  - A click on a subject of the Subjects view opens it; a click on "From push_swap.pdf, page 3" of a check opens it at that page.
//  - The pages come from the web app (the same images the old browser UI showed), one at a time and only when they are near the
//    screen, so a 40-page subject opens at once. The page is plain images: no PDF is ever run (see pdf-page.ts).
//  - One tab per PDF: opening it again goes to that tab, at the page asked for.

import * as crypto from "node:crypto";
import * as vscode from "vscode";
import type { SessionState } from "../../session/session-state";
import { pageHtml } from "./pdf-page";

export const MAX_PAGES = 400;

/** One page of a subject as a PNG. */
export type PageFetcher = (name: string, page: number) => Promise<Buffer>;

const pageOf = (value: unknown, pages: number): number => Math.min(Math.max(Number.isInteger(Number(value)) ? Number(value) : 1, 1), pages);

export class PdfViewer {
  private readonly panels = new Map<string, vscode.WebviewPanel>();           // subject name -> its tab

  constructor(private readonly session: SessionState, private readonly fetchPage: PageFetcher) {}

  /** Open (or go to) the PDF of a subject of the review. */
  async open(name: string | undefined, page?: unknown): Promise<void> {
    const subject = (this.session.current?.subjects ?? []).find((s) => s.name === name);
    if (!subject) throw new Error(`${name || "that PDF"} is not a subject of this review`);
    const pages = Math.min(Number(subject.pages) || 0, MAX_PAGES);
    if (!pages) throw new Error(`${subject.name} has no pages to show`);
    const target = pageOf(page, pages);
    const existing = this.panels.get(subject.name);
    if (!existing) {
      this.create(subject.name, pages, target);
      return;
    }
    existing.reveal();
    void existing.webview.postMessage({ t: "goto", page: target });
  }

  /** After the review's subjects changed: a tab of a subject that is gone is closed. */
  sync(): void {
    const have = new Set((this.session.current?.subjects ?? []).map((s) => s.name));
    for (const [name, panel] of [...this.panels]) if (!have.has(name)) panel.dispose();
  }

  private create(name: string, pages: number, page: number): void {
    const panel = vscode.window.createWebviewPanel("verdict.subject", name, vscode.ViewColumn.Active,
      { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [] });
    this.panels.set(name, panel);
    panel.onDidDispose(() => { if (this.panels.get(name) === panel) this.panels.delete(name); });
    panel.webview.onDidReceiveMessage((message: unknown) => this.answer(panel, name, pages, message));
    panel.webview.html = pageHtml(crypto.randomBytes(16).toString("hex"), { name, pages, page });
  }

  /** The page asks for a page image; only the pages that exist are answered (the message is from a page, not to be trusted). */
  private async answer(panel: vscode.WebviewPanel, name: string, pages: number, message: unknown): Promise<void> {
    const ask = message as { t?: unknown; n?: unknown } | null;
    const n = ask?.n;
    if (ask?.t !== "page" || typeof n !== "number" || !Number.isInteger(n) || n < 1 || n > pages) return;
    try {
      const png = await this.fetchPage(name, n);
      void panel.webview.postMessage({ t: "page", n, src: `data:image/png;base64,${png.toString("base64")}` });
    } catch (err) {
      void panel.webview.postMessage({ t: "error", n, text: String((err as Error).message || err).slice(0, 200) });
    }
  }

  register(): vscode.Disposable[] {
    return [vscode.commands.registerCommand("verdict.openSubject", async (arg?: string | { subject?: string }, page?: unknown) => {
      const name = typeof arg === "string" ? arg : arg?.subject;
      try {
        await this.open(name, page);
      } catch (err) {
        void vscode.window.showErrorMessage(`Verdict: ${(err as Error).message}`);
      }
    })];
  }
}
