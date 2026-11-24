import type { Environment, EnvironmentPart } from "../api/types";

const PARTS: Array<["sandbox" | "terminal", string]> = [
  ["sandbox", "Sandbox (runs the checks, no network)"],
  ["terminal", "Terminal (this editor, claude)"],
];

function partLines(part: EnvironmentPart | undefined, title: string): string[] {
  const lines = [`## ${title}`, ""];
  if (!part?.available) lines.push(`✖ ${part?.error || "not available"}`, "");
  for (const tool of part?.tools ?? []) lines.push(`- ${tool.ok ? "✔" : tool.required ? "✖" : "⚠"} **${tool.name}**: ${String(tool.detail || "").replace(/\s+/g, " ")}`);
  lines.push("");
  return lines;
}

/** The environment check as a markdown page: the sandbox and the terminal, each tool with its mark. */
export function environmentMarkdown(env: Environment): string {
  const lines = [`# The environment: ${env.ready ? "ready" : "NOT ready"}`, ""];
  for (const [key, title] of PARTS) lines.push(...partLines(env[key], title));
  lines.push("Only ✖ makes it not ready.");
  return lines.join("\n");
}
