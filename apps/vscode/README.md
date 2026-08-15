# CodeHub VS Code Extension

One Agent. Every Model.

## Prerequisites

1. Install the Python package from the repo root:

```bash
cd /path/to/codehub
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill at least one API key
```

2. Node 18+ for building the extension.

## Develop / Run

```bash
cd apps/vscode
npm install
npm run compile
```

Then in VS Code / Cursor:

1. Open the **codehub** repo as the workspace
2. Open `apps/vscode` and press **F5** (Run Extension), **or**
3. Install the compiled extension via “Install from VSIX” after packaging

Commands:

- `CodeHub: Open Chat`
- `CodeHub: Start Local Agent Server`
- `CodeHub: Show File Diff`
- `CodeHub: Keep All Changes`
- `CodeHub: Revert All Changes`
- `CodeHub: Ask about Selection`

After the agent writes files, the Chat panel lists each change with **Diff / Keep / Revert** (plus Keep all / Revert all). Files are already on disk; **Revert** restores the previous contents (or deletes a newly created file).

Settings (`codehub.*`):

- `serverUrl` (default `http://127.0.0.1:8765`)
- `pythonPath` (optional)
- `autoStartServer`
- `maxSteps`
- BYOK keys: `deepseekApiKey`, `qwenApiKey`, `glmApiKey`, `kimiApiKey`

## Manual server

```bash
codehub serve
# or
codehub-server
```

Health check: `GET http://127.0.0.1:8765/health`
