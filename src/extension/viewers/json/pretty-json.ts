// JSON that can be read. A file saved on one line (an export, a minified config) is opened by the extension as a pretty-printed
// view, read-only, and never written back: the file on disk is not touched. No vscode here (the editor side is json-viewer.ts).

export const MAX_BYTES = 2 * 1024 * 1024;
const LONG_LINE = 160;

const BLANK = /\s/;
const END_OF_SCALAR = /[\s,:{}[\]"]/;

/** Writes a JSON text out again, one value per line and indented, token by token. The text of every number and string is kept
 * exactly as it is. The text must be valid JSON (`pretty` checks that first). */
class Printer {
  private out = "";
  private depth = 0;
  private at = 0;

  constructor(private readonly src: string, private readonly unit: string) {}

  run(): string {
    for (; this.at < this.src.length; this.at++) {
      const c = this.src[this.at];
      if (BLANK.test(c)) continue;
      if (c === '"') this.string();
      else if (c === "{" || c === "[") this.open(c);
      else if (c === "}" || c === "]") { this.depth--; this.out += this.newline() + c; }
      else if (c === ",") this.out += "," + this.newline();
      else if (c === ":") this.out += ": ";
      else this.scalar();
    }
    return this.out + "\n";
  }

  private newline(): string { return `\n${this.unit.repeat(this.depth)}`; }

  private string(): void {
    let end = this.at + 1;
    while (this.src[end] !== '"') end += this.src[end] === "\\" ? 2 : 1;
    this.out += this.src.slice(this.at, end + 1);
    this.at = end;
  }

  /** An empty object or array stays on one line. */
  private open(c: string): void {
    let next = this.at + 1;
    while (BLANK.test(this.src[next])) next++;
    if (this.src[next] === (c === "{" ? "}" : "]")) {
      this.out += c + this.src[next];
      this.at = next;
    } else {
      this.depth++;
      this.out += c + this.newline();
    }
  }

  private scalar(): void {
    let end = this.at;
    while (end < this.src.length && !END_OF_SCALAR.test(this.src[end])) end++;
    this.out += this.src.slice(this.at, end);
    this.at = end - 1;
  }
}

/** The same JSON, one value per line, indented (keys in the file's order, no rounding of big numbers). Null when `text` is not JSON. */
export function pretty(text: string, unit = "  "): string | null {
  const src = text.replace(/^\uFEFF/, "");
  try { JSON.parse(src); } catch { return null; }
  return new Printer(src, unit).run();
}

const lines = (text: string): number => text.split("\n").length;
const longest = (text: string): number => Math.max(...text.split("\n").map((line) => line.length));

/** Is this a JSON file that is hard to read as it is: some line is very long, and printing it out gives many more lines and
 * much shorter ones (a file with one long string in it is not made easier to read by it). */
export function looksMinified(text: string): boolean {
  if (text.length > MAX_BYTES || longest(text) <= LONG_LINE) return false;
  const shown = pretty(text);
  return shown !== null && lines(shown) >= 2 * lines(text) && longest(shown) <= longest(text) / 2;
}
