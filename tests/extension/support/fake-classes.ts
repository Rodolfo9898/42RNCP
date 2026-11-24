// The value classes of the fake `vscode` module: the ones the extension builds (addresses, icons, tree rows) and listens through.

export class EventEmitter<T> {
  private listeners: Array<(value: T) => unknown> = [];
  readonly event = (fn: (value: T) => unknown): { dispose(): void } => {
    this.listeners.push(fn);
    return { dispose: () => { this.listeners = this.listeners.filter((l) => l !== fn); } };
  };
  fire(value?: T): void { for (const fn of [...this.listeners]) fn(value as T); }
  dispose(): void { this.listeners = []; }
}

export class Uri {
  constructor(readonly scheme: string, readonly path: string, readonly query = "") {}
  static file(p: string): Uri { return new Uri("file", p); }
  static from(parts: { scheme: string; path: string; query?: string }): Uri { return new Uri(parts.scheme, parts.path, parts.query || ""); }
  get fsPath(): string { return this.path; }
  toString(): string { return `${this.scheme}:${this.path}${this.query ? `?${this.query}` : ""}`; }
}

export class TabInputText { constructor(readonly uri: Uri) {} }
export class TabInputCustom { constructor(readonly uri: Uri, readonly viewType: string) {} }
export class ThemeIcon { constructor(readonly id: string, readonly color?: ThemeColor) {} }
export class ThemeColor { constructor(readonly id: string) {} }
export class TreeItem {
  description?: string;
  tooltip?: unknown;
  iconPath?: unknown;
  command?: { command: string; title: string; arguments?: unknown[] };
  contextValue?: string;
  constructor(readonly label: string, readonly collapsibleState?: number) {}
}
export class MarkdownString { value = ""; appendText(text: string): this { this.value = text; return this; } }
export class Range {
  readonly start: { line: number; character: number };
  readonly end: { line: number; character: number };
  constructor(a: number, b: number, c: number, d: number) { this.start = { line: a, character: b }; this.end = { line: c, character: d }; }
}
