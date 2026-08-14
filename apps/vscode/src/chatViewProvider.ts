import * as vscode from "vscode";
import * as path from "path";
import {
  AgentClient,
  FileChange,
  WorkspaceContextPayload,
  collectApiKeys,
} from "./agentClient";
import { ServerManager } from "./serverManager";

interface WebviewMessage {
  type: string;
  prompt?: string;
  path?: string;
}

export class ChatViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "codehub.chatView";
  private view?: vscode.WebviewView;
  private lastChanges: FileChange[] = [];

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly client: AgentClient,
    private readonly server: ServerManager
  ) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.context.extensionUri],
    };
    webviewView.webview.html = this.getHtml(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (msg: WebviewMessage) => {
      if (msg.type === "submit" && msg.prompt?.trim()) {
        await this.handlePrompt(msg.prompt.trim());
      } else if (msg.type === "showDiff" && msg.path) {
        await this.showDiff(msg.path);
      } else if (msg.type === "openSettings") {
        await vscode.commands.executeCommand(
          "workbench.action.openSettings",
          "@ext:codehub.codehub"
        );
      } else if (msg.type === "ready") {
        await this.pushStatus();
      }
    });
  }

  async ask(prompt: string): Promise<void> {
    if (this.view) {
      this.view.show?.(true);
    }
    await this.handlePrompt(prompt);
  }

  getLastChanges(): FileChange[] {
    return this.lastChanges;
  }

  async showDiff(relativePath: string): Promise<void> {
    const change = this.lastChanges.find((c) => c.path === relativePath);
    if (!change) {
      vscode.window.showWarningMessage(`No CodeHub change recorded for ${relativePath}`);
      return;
    }
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
      return;
    }
    const before = change.before ?? "";
    const after = change.after ?? "";
    const left = vscode.Uri.parse(
      `codehub-diff:before/${relativePath}?${encodeURIComponent(before)}`
    );
    const right = vscode.Uri.joinPath(folder.uri, relativePath);
    await vscode.commands.executeCommand(
      "vscode.diff",
      left,
      right,
      `CodeHub: ${relativePath} (${change.action})`
    );
  }

  private async pushStatus(): Promise<void> {
    const healthy = await this.server.isHealthy();
    this.post({ type: "status", healthy });
  }

  private async handlePrompt(prompt: string): Promise<void> {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
      this.post({ type: "error", message: "Open a workspace folder first." });
      return;
    }

    this.post({ type: "user", content: prompt });
    this.post({ type: "status", running: true, healthy: true });

    try {
      await this.server.ensureRunning();
      const cfg = vscode.workspace.getConfiguration("codehub");
      const maxSteps = cfg.get<number>("maxSteps") ?? 12;
      const context = this.collectWorkspaceContext(folder.uri.fsPath);

      const result = await this.client.run({
        prompt,
        workspace: folder.uri.fsPath,
        maxSteps,
        apiKeys: collectApiKeys(),
        context,
        onEvent: (type, payload) => {
          if (type === "model_response") {
            this.post({
              type: "event",
              content: `→ ${payload.provider}/${payload.model} step=${payload.step}`,
            });
          } else if (type === "tool_result") {
            this.post({
              type: "event",
              content: `⚙ ${payload.tool}: ${String(payload.preview || "").slice(0, 120)}`,
            });
          }
        },
      });

      this.lastChanges = result.file_changes || [];
      this.post({
        type: "assistant",
        content: result.content,
        meta: `${result.provider}/${result.model} · steps=${result.steps} · tools=${result.tool_calls}`,
        changes: this.lastChanges.map((c) => ({ path: c.path, action: c.action })),
      });

      // Refresh editors for written files.
      for (const change of this.lastChanges) {
        const uri = vscode.Uri.joinPath(folder.uri, change.path);
        try {
          await vscode.workspace.openTextDocument(uri);
        } catch {
          /* ignore missing */
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.post({ type: "error", message });
    } finally {
      this.post({ type: "status", running: false });
      await this.pushStatus();
    }
  }

  private collectWorkspaceContext(workspaceRoot: string): WorkspaceContextPayload {
    const toRel = (uri: vscode.Uri): string => {
      const rel = path.relative(workspaceRoot, uri.fsPath);
      return rel && !rel.startsWith("..") ? rel : path.basename(uri.fsPath);
    };

    const open_files = vscode.window.visibleTextEditors
      .filter((e) => e.document.uri.scheme === "file")
      .slice(0, 5)
      .map((editor) => {
        const selection = editor.document.getText(editor.selection);
        const content =
          selection.trim().length > 0
            ? undefined
            : editor.document.getText().slice(0, 8000);
        return {
          path: toRel(editor.document.uri),
          language: editor.document.languageId,
          selection: selection.trim() ? selection.slice(0, 6000) : undefined,
          content,
        };
      });

    const active = vscode.window.activeTextEditor;
    let active_file: WorkspaceContextPayload["active_file"];
    if (active && active.document.uri.scheme === "file") {
      const selection = active.document.getText(active.selection);
      active_file = {
        path: toRel(active.document.uri),
        language: active.document.languageId,
        selection: selection.trim() ? selection.slice(0, 6000) : undefined,
        content:
          selection.trim().length > 0
            ? undefined
            : active.document.getText().slice(0, 8000),
      };
    }

    return {
      active_file,
      open_files,
      max_depth: 2,
    };
  }

  private post(message: Record<string, unknown>): void {
    void this.view?.webview.postMessage(message);
  }

  private getHtml(webview: vscode.Webview): string {
    const nonce = getNonce();
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CodeHub</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: var(--vscode-sideBar-background);
      --fg: var(--vscode-foreground);
      --muted: var(--vscode-descriptionForeground);
      --border: var(--vscode-panel-border, rgba(127,127,127,.35));
      --input: var(--vscode-input-background);
      --input-fg: var(--vscode-input-foreground);
      --btn: var(--vscode-button-background);
      --btn-fg: var(--vscode-button-foreground);
      --accent: #3ecf8e;
    }
    body {
      margin: 0;
      padding: 0;
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      color: var(--fg);
      background: var(--bg);
      display: flex;
      flex-direction: column;
      height: 100vh;
    }
    header {
      padding: 10px 12px 8px;
      border-bottom: 1px solid var(--border);
    }
    header h1 {
      margin: 0;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    header p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 11px;
    }
    #status {
      margin-top: 6px;
      font-size: 11px;
      color: var(--muted);
    }
    #status.ok { color: var(--accent); }
    #status.bad { color: #e36; }
    #log {
      flex: 1;
      overflow: auto;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .bubble {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.45;
    }
    .bubble.user { border-left: 3px solid var(--accent); }
    .bubble.assistant { border-left: 3px solid #5b9cff; }
    .bubble.event, .bubble.error {
      border-style: dashed;
      color: var(--muted);
      font-size: 11px;
    }
    .bubble.error { color: #e36; border-color: #e36; }
    .meta { margin-top: 6px; font-size: 11px; color: var(--muted); }
    .changes { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
    .changes button {
      text-align: left;
      background: transparent;
      color: var(--fg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 4px 8px;
      cursor: pointer;
      font-size: 11px;
    }
    form {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 10px 12px 12px;
      border-top: 1px solid var(--border);
    }
    textarea {
      width: 100%;
      min-height: 72px;
      resize: vertical;
      box-sizing: border-box;
      background: var(--input);
      color: var(--input-fg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px;
      font: inherit;
    }
    .row { display: flex; gap: 8px; }
    button.send, button.link {
      border: none;
      border-radius: 6px;
      padding: 6px 10px;
      cursor: pointer;
      font: inherit;
    }
    button.send {
      background: var(--btn);
      color: var(--btn-fg);
      flex: 1;
    }
    button.send:disabled { opacity: 0.5; cursor: default; }
    button.link {
      background: transparent;
      color: var(--muted);
      border: 1px solid var(--border);
    }
  </style>
</head>
<body>
  <header>
    <h1>CodeHub</h1>
    <p>One Agent. Every Model.</p>
    <div id="status">checking server…</div>
  </header>
  <div id="log"></div>
  <form id="form">
    <textarea id="prompt" placeholder="Describe a coding task…"></textarea>
    <div class="row">
      <button class="send" id="send" type="submit">Run Agent</button>
      <button class="link" id="settings" type="button">Settings</button>
    </div>
  </form>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const log = document.getElementById('log');
    const form = document.getElementById('form');
    const promptEl = document.getElementById('prompt');
    const sendBtn = document.getElementById('send');
    const statusEl = document.getElementById('status');

    function addBubble(cls, text, extra) {
      const div = document.createElement('div');
      div.className = 'bubble ' + cls;
      div.textContent = text || '';
      if (extra) div.appendChild(extra);
      log.appendChild(div);
      log.scrollTop = log.scrollHeight;
      return div;
    }

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const prompt = promptEl.value.trim();
      if (!prompt || sendBtn.disabled) return;
      vscode.postMessage({ type: 'submit', prompt });
      promptEl.value = '';
    });
    document.getElementById('settings').addEventListener('click', () => {
      vscode.postMessage({ type: 'openSettings' });
    });

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg.type === 'user') addBubble('user', msg.content);
      if (msg.type === 'assistant') {
        const wrap = document.createElement('div');
        if (msg.meta) {
          const meta = document.createElement('div');
          meta.className = 'meta';
          meta.textContent = msg.meta;
          wrap.appendChild(meta);
        }
        if (msg.changes && msg.changes.length) {
          const box = document.createElement('div');
          box.className = 'changes';
          msg.changes.forEach((c) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = c.action + ': ' + c.path + ' (diff)';
            b.addEventListener('click', () => vscode.postMessage({ type: 'showDiff', path: c.path }));
            box.appendChild(b);
          });
          wrap.appendChild(box);
        }
        const bubble = addBubble('assistant', msg.content);
        bubble.appendChild(wrap);
      }
      if (msg.type === 'event') addBubble('event', msg.content);
      if (msg.type === 'error') addBubble('error', msg.message);
      if (msg.type === 'status') {
        if (msg.running) {
          sendBtn.disabled = true;
          statusEl.textContent = 'agent running…';
          statusEl.className = '';
        } else {
          sendBtn.disabled = false;
        }
        if (msg.healthy === true) {
          statusEl.textContent = 'server connected';
          statusEl.className = 'ok';
        } else if (msg.healthy === false) {
          statusEl.textContent = 'server offline';
          statusEl.className = 'bad';
        }
      }
    });

    vscode.postMessage({ type: 'ready' });
  </script>
</body>
</html>`;
  }
}

export class DiffContentProvider implements vscode.TextDocumentContentProvider {
  provideTextDocumentContent(uri: vscode.Uri): string {
    // URI: codehub-diff:before/path?urlencodedContent
    try {
      return decodeURIComponent(uri.query || "");
    } catch {
      return uri.query || "";
    }
  }
}

function getNonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let text = "";
  for (let i = 0; i < 32; i++) {
    text += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return text;
}
