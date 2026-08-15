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
    const monorepo = this.isCodehubMonorepo(repoRoot);
    const cwd =
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || repoRoot;
    const url = vscode.workspace.getConfiguration("codehub").get<string>("serverUrl") ||
      "http://127.0.0.1:8765";
    const port = new URL(url).port || "8765";

    this.output.appendLine(`Starting CodeHub server with: ${python}`);
    this.output.appendLine(`Working directory: ${cwd}`);
    if (monorepo) {
      this.output.appendLine(`Monorepo PYTHONPATH: ${repoRoot}`);
    }

    const env: NodeJS.ProcessEnv = { ...process.env };
    if (monorepo) {
      env.PYTHONPATH = repoRoot;
    }

    this.process = spawn(
      python,
      ["-m", "uvicorn", "codehub.server:app", "--host", "127.0.0.1", "--port", port],
      {
        cwd,
        env,
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
    const roots = new Set<string>();
    roots.add(this.resolveRepoRoot());
    for (const folder of vscode.workspace.workspaceFolders || []) {
      roots.add(folder.uri.fsPath);
    }
    const candidates: string[] = [];
    for (const root of roots) {
      candidates.push(path.join(root, ".venv", "bin", "python"));
      candidates.push(path.join(root, ".venv", "Scripts", "python.exe"));
    }
    candidates.push("python3", "python");
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

  private isCodehubMonorepo(root: string): boolean {
    const pyproject = path.join(root, "pyproject.toml");
    if (!fs.existsSync(pyproject)) {
      return false;
    }
    try {
      return fs.readFileSync(pyproject, "utf8").includes('name = "codehub"');
    } catch {
      return false;
    }
  }

  private resolveRepoRoot(): string {
    // Prefer workspace folder that contains pyproject with name codehub.
    const folders = vscode.workspace.workspaceFolders || [];
    for (const folder of folders) {
      if (this.isCodehubMonorepo(folder.uri.fsPath)) {
        return folder.uri.fsPath;
      }
    }
    // Extension may live at apps/vscode inside the monorepo (F5 / symlink).
    const extRoot = this.context.extensionPath;
    const maybeRoot = path.resolve(extRoot, "..", "..");
    if (this.isCodehubMonorepo(maybeRoot)) {
      return maybeRoot;
    }
    if (folders[0]) {
      return folders[0].uri.fsPath;
    }
    return maybeRoot;
  }
}
