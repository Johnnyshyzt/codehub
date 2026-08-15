# CodeHub VS Code Extension

One Agent. Every Model.

## Install from VSIX (recommended for now)

The extension is not on the Marketplace yet. Build or download a `.vsix`, then install it.

### Build locally

```bash
# 1) Python agent (required — the extension talks to a local server)
cd /path/to/codehub
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill at least one API key

# 2) Package the extension
cd apps/vscode
npm install
npm run package
# → codehub-0.3.0.vsix
```

### Install the `.vsix`

**VS Code / Cursor**

1. Command Palette → **Extensions: Install from VSIX…**
2. Select `apps/vscode/codehub-0.3.0.vsix`
3. Reload the window

**CLI**

```bash
code --install-extension apps/vscode/codehub-0.3.0.vsix
# Cursor:
# cursor --install-extension apps/vscode/codehub-0.3.0.vsix
```

### After install

1. Open any workspace (or the CodeHub repo).
2. Set `codehub.pythonPath` to your venv Python if auto-detect fails  
   (e.g. `/path/to/codehub/.venv/bin/python`).
3. Ensure at least one provider key is available via `.env` next to the package,  
   process env, or Settings (`codehub.deepseekApiKey`, etc.).
4. Open the **CodeHub** activity-bar panel and send a task.  
   With `autoStartServer` (default), the local agent starts on `:8765`.

You can also start the server yourself:

```bash
codehub serve
```

## Develop / F5

```bash
cd apps/vscode
npm install
npm run compile
```

Open the **codehub** repo as the workspace, then press **F5** (Run Extension).

## Commands

- `CodeHub: Open Chat`
- `CodeHub: Start Local Agent Server`
- `CodeHub: Stop Local Agent Server`
- `CodeHub: Show File Diff`
- `CodeHub: Keep All Changes`
- `CodeHub: Revert All Changes`
- `CodeHub: Ask about Selection`

After the agent writes files, the Chat panel lists each change with **Diff / Keep / Revert** (plus Keep all / Revert all). Files are already on disk; **Revert** restores the previous contents (or deletes a newly created file). Diff snapshots are held in memory (not URI query), so large files work.

While a run is in progress, use **Cancel** to stop. If the server is offline or no API keys are configured, the panel shows a guidance banner with **Start server** / **Open Settings**.

The header also shows live **usage / mcp / scores** summaries from the local API.

## Settings (`codehub.*`)

| Setting | Default | Notes |
|---------|---------|--------|
| `serverUrl` | `http://127.0.0.1:8765` | Local agent API |
| `pythonPath` | _(empty)_ | Prefer your `.venv/bin/python` |
| `autoStartServer` | `true` | Spawn uvicorn on activate |
| `maxSteps` | `12` | Tool-loop cap |
| `deepseekApiKey` / `qwenApiKey` / `glmApiKey` / `kimiApiKey` | | BYOK overrides |

## Manual server

```bash
codehub serve
# or
codehub-server
```

Health check: `GET http://127.0.0.1:8765/health`

## Packaging notes

- `npm run package` uses `@vscode/vsce` and writes `codehub-<version>.vsix` in `apps/vscode/`.
- `.vsix` files are gitignored; publish artifacts from CI or release attachments.
- Marketplace publish (`vsce publish`) is deferred until a publisher account is set up.
