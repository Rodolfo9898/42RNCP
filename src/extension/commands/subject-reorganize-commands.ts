import * as vscode from "vscode";
import type { VerdictApi } from "../api/verdict-api";
import type { ChannelLog } from "../output/channel-log";
import type { CommandGroup, CommandRegistry } from "./registry";

const MOVE = "Move";

/** The PDFs and artifacts that are on disk go into the folder of their series (samples/common-core/cpp00.pdf into
 * samples/common-core/cpp-modules/): the app says what it would move (a dry run), and moves it once the person agrees. */
export class SubjectReorganizeCommands implements CommandGroup {
  constructor(private readonly api: VerdictApi, private readonly log: ChannelLog) {}

  register(commands: CommandRegistry): vscode.Disposable[] {
    return [commands.guarded("verdict.subjectsReorganize", () => this.run())];
  }

  async run(): Promise<void> {
    const { moves } = await this.api.reorganize(true);
    if (!moves.length) {
      void vscode.window.showInformationMessage("Every PDF and artifact is already in the folder of its series.");
      return;
    }
    this.log.block(["To move into the folders of their series:", ...moves.map((move) => `  ${move.from} → ${move.to}`)]);
    this.log.show(true);
    const go = await vscode.window.showInformationMessage(`${moves.length} PDFs and artifact folders will move into the folders of their series (see the output)`,
      { modal: true }, MOVE);
    if (go !== MOVE) return;
    const { done } = await this.api.reorganize(false);
    const text = `Moved ${done} PDFs and artifact folders into the folders of their series.`;
    this.log.line(text);
    void vscode.window.showInformationMessage(text);
  }
}
