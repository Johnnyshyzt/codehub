import * as vscode from "vscode";
import { AgentClient } from "./agentClient";
import { ChatViewProvider, DiffContentProvider } from "./chatViewProvider";
import { ServerManager } from "./serverManager";

export function activate(context: vscode.ExtensionContext): void {
  const client = new AgentClient(() => {
    return (
      vscode.workspace.getConfiguration("codehub").get<string>("serverUrl") ||
      "http://127.0.0.1:8765"
    );
  });
  const server = new ServerManager(context, client);
  const chat = new ChatViewProvider(context, client, server);
  const diffProvider = new DiffContentProvider();

  context.subscriptions.push(
    server,
    vscode.window.registerWebviewViewProvider(ChatViewProvider.viewType, chat),
    vscode.workspace.registerTextDocumentContentProvider("codehub-diff", diffProvider),
    vscode.commands.registerCommand("codehub.openChat", async () => {
      await vscode.commands.executeCommand("codehub.chatView.focus");
    }),
    vscode.commands.registerCommand("codehub.startServer", async () => {
      try {
        await server.start();
        await server.ensureRunning();
        vscode.window.showInformationMessage("CodeHub server is running.");
      } catch (err) {
        vscode.window.showErrorMessage(
          err instanceof Error ? err.message : String(err)
        );
      }
    }),
    vscode.commands.registerCommand("codehub.stopServer", () => {
      server.stop();
      vscode.window.showInformationMessage("CodeHub server stopped.");
    }),
    vscode.commands.registerCommand("codehub.showDiff", async () => {
      const changes = chat.getLastChanges();
      if (!changes.length) {
        vscode.window.showInformationMessage("No CodeHub file changes yet.");
        return;
      }
      const picked = await vscode.window.showQuickPick(
        changes.map((c) => ({ label: c.path, description: c.action })),
        { placeHolder: "Select a changed file" }
      );
      if (picked) {
        await chat.showDiff(picked.label);
      }
    }),
    vscode.commands.registerCommand("codehub.keepAllChanges", async () => {
      const pending = chat.getLastChanges().filter((c) => c.decision === "pending");
      if (!pending.length) {
        vscode.window.showInformationMessage("No pending CodeHub changes to keep.");
        return;
      }
      await chat.keepAll();
      vscode.window.showInformationMessage(`Kept ${pending.length} CodeHub change(s).`);
    }),
    vscode.commands.registerCommand("codehub.revertAllChanges", async () => {
      const pending = chat.getLastChanges().filter((c) => c.decision === "pending");
      if (!pending.length) {
        vscode.window.showInformationMessage("No pending CodeHub changes to revert.");
        return;
      }
      const confirm = await vscode.window.showWarningMessage(
        `Revert ${pending.length} CodeHub change(s)?`,
        { modal: true },
        "Revert"
      );
      if (confirm === "Revert") {
        await chat.revertAll();
      }
    }),
    vscode.commands.registerCommand("codehub.askSelection", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.selection.isEmpty) {
        vscode.window.showWarningMessage("Select some code first.");
        return;
      }
      const selected = editor.document.getText(editor.selection);
      await chat.ask(
        `Explain and improve this code if needed. Keep changes minimal.\n\n\`\`\`\n${selected}\n\`\`\``
      );
    })
  );

  const auto = vscode.workspace
    .getConfiguration("codehub")
    .get<boolean>("autoStartServer");
  if (auto) {
    void server.ensureRunning().catch((err) => {
      console.warn("CodeHub auto-start failed:", err);
    });
  }
}

export function deactivate(): void {
  // ServerManager disposed via subscriptions.
}
