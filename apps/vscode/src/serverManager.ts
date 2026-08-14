import * as vscode from "vscode";
import { spawn, ChildProcessWithoutNullStreams } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { AgentClient } from "./agentClient";

export class ServerManager implements vscode.Disposable {
  private process: ChildProcessWithoutNullStreams | undefined;
  private readonly output: vscode.OutputChannel;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly client: AgentClient
  ) {
    this.output = vscode.window.createOutputChannel("CodeHub");
  }

  dispose(): void {
    this.stop();
    this.output.dispose();
  }

  async ensureRunning(): Promise<void> {
    if (await this.isHealthy()) {
      return;
    }
    const auto = vscode.workspace.getConfiguration("codehub").get<boolean>("autoStartServer");
    if (!auto) {
      throw new Error(
        "CodeHub server is not running. Run “CodeHub: Start Local Agent Server” or enable autoStartServer."
      );
    }
    await this.start();
    await this.waitHealthy(20_000);
  }

  async isHealthy(): Promise<boolean> {
    try {
      const h = await this.client.health();
      return !!h.ok;
    } catch {
      return false;
    }
  }

  async start(): Promise<void> {
    if (this.process && !this.process.killed) {
      return;
    }
    const python = this.resolvePython();
    const repoRoot = this.resolveRepoRoot();
    const url = vscode.workspace.getConfiguration("codehub").get<string>("serverUrl") ||
      "http://127.0.0.1:8765";
    const port = new URL(url).port || "8765";

    this.output.appendLine(`Starting CodeHub server with: ${python}`);
    this.output.appendLine(`Repo root: ${repoRoot}`);

    this.process = spawn(
      python,
      ["-m", "uvicorn", "codehub.server:app", "--host", "127.0.0.1", "--port", port],
      {
        cwd: repoRoot,
        env: {
          ...process.env,
          PYTHONPATH: repoRoot,
        },
      }
    );

    this.process.stdout.on("data", (d) => this.output.append(d.toString()));
    this.process.stderr.on("data", (d) => this.output.append(d.toString()));
    this.process.on("exit", (code) => {
      this.output.appendLine(`Server exited with code ${code}`);
      this.process = undefined;
    });

    this.context.subscriptions.push({
      dispose: () => this.stop(),
    });
  }

  stop(): void {
    if (this.process && !this.process.killed) {
      this.process.kill();
      this.process = undefined;
    }
  }

  private async waitHealthy(timeoutMs: number): Promise<void> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (await this.isHealthy()) {
        return;
      }
      await new Promise((r) => setTimeout(r, 400));
    }
    throw new Error(
      "CodeHub server failed to become healthy. Check the “CodeHub” output channel and that the package is installed (`pip install -e .`)."
    );
  }

  private resolvePython(): string {
    const configured = vscode.workspace
      .getConfiguration("codehub")
      .get<string>("pythonPath")
      ?.trim();
    if (configured) {
      return configured;
    }
    const repoRoot = this.resolveRepoRoot();
    const candidates = [
      path.join(repoRoot, ".venv", "bin", "python"),
      path.join(repoRoot, ".venv", "Scripts", "python.exe"),
      "python3",
      "python",
    ];
    for (const c of candidates) {
      if (c === "python3" || c === "python") {
        return c;
      }
      if (fs.existsSync(c)) {
        return c;
      }
    }
    return "python3";
  }

  private resolveRepoRoot(): string {
    // Prefer workspace folder that contains pyproject with name codehub.
    const folders = vscode.workspace.workspaceFolders || [];
    for (const folder of folders) {
      const pyproject = path.join(folder.uri.fsPath, "pyproject.toml");
      if (fs.existsSync(pyproject)) {
        const text = fs.readFileSync(pyproject, "utf8");
        if (text.includes('name = "codehub"')) {
          return folder.uri.fsPath;
        }
      }
    }
    // Extension may live at apps/vscode inside the monorepo.
    const extRoot = this.context.extensionPath;
    const maybeRoot = path.resolve(extRoot, "..", "..");
    if (fs.existsSync(path.join(maybeRoot, "pyproject.toml"))) {
      return maybeRoot;
    }
    if (folders[0]) {
      return folders[0].uri.fsPath;
    }
    return maybeRoot;
  }
}
