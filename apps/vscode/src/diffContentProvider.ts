import * as vscode from "vscode";

/**
 * Virtual documents for CodeHub diffs.
 * Content is kept in memory — never put large file bodies in URI query strings.
 */
export class DiffContentProvider
  implements vscode.TextDocumentContentProvider, vscode.Disposable
{
  public static readonly scheme = "codehub-diff";

  private readonly contents = new Map<string, string>();
  private readonly emitter = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this.emitter.event;

  dispose(): void {
    this.contents.clear();
    this.emitter.dispose();
  }

  provideTextDocumentContent(uri: vscode.Uri): string {
    return this.contents.get(this.keyFromUri(uri)) ?? "";
  }

  /** URI for the "before" side of a change. */
  uriBefore(relativePath: string): vscode.Uri {
    return this.makeUri("before", relativePath);
  }

  /** URI for an in-memory "after" side (when the disk file is missing). */
  uriAfter(relativePath: string): vscode.Uri {
    return this.makeUri("after", relativePath);
  }

  setBefore(relativePath: string, content: string): vscode.Uri {
    const uri = this.uriBefore(relativePath);
    this.contents.set(this.keyFromUri(uri), content);
    this.emitter.fire(uri);
    return uri;
  }

  setAfter(relativePath: string, content: string): vscode.Uri {
    const uri = this.uriAfter(relativePath);
    this.contents.set(this.keyFromUri(uri), content);
    this.emitter.fire(uri);
    return uri;
  }

  /** Replace stored snapshots for the latest agent file_changes batch. */
  syncFromChanges(
    changes: Array<{ path: string; before?: string | null; after?: string | null }>
  ): void {
    this.contents.clear();
    for (const change of changes) {
      this.setBefore(change.path, change.before ?? "");
      if (change.after != null) {
        this.setAfter(change.path, change.after);
      }
    }
  }

  clear(): void {
    this.contents.clear();
  }

  private makeUri(side: "before" | "after", relativePath: string): vscode.Uri {
    const normalized = relativePath.replace(/\\/g, "/").replace(/^\/+/, "");
    return vscode.Uri.from({
      scheme: DiffContentProvider.scheme,
      path: `/${side}/${normalized}`,
    });
  }

  private keyFromUri(uri: vscode.Uri): string {
    return uri.path.replace(/^\/+/, "");
  }
}
