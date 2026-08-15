# Release checklist (V0.3)

Local-first release — **no CodeHub cloud server required**.

## Before you publish

- [ ] `pytest -q` and `ruff check .` pass
- [ ] `codehub bench` (mock) is 8/8
- [ ] `cd apps/vscode && npm run package` builds `codehub-0.3.0.vsix`
- [ ] Version aligned: `pyproject.toml` / `codehub.__version__` / extension `package.json` = `0.3.0`
- [ ] CHANGELOG.md entry for this version looks right
- [ ] No secrets in git (`.env`, PATs, API keys)

## 1) Publish source (GitHub)

```bash
git push -u origin main
```

Confirm Actions → **CI** is green.

Optional: add repo secrets for nightly live bench  
(`DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY` / `QWEN_API_KEY`, `ZHIPU_API_KEY` / `GLM_API_KEY`, `MOONSHOT_API_KEY` / `KIMI_API_KEY`),  
then run **Nightly live bench** via Actions → workflow_dispatch.

## 2) Publish VS Code extension (optional)

Still local-first: users install the VSIX and run `pip install` + API keys on their machine.

```bash
cd apps/vscode
npm run package
# Install locally:
#   code --install-extension codehub-0.3.0.vsix
```

Marketplace / Open VSX (when a publisher account exists):

```bash
# VS Marketplace (needs Personal Access Token with Marketplace scope)
npx vsce login <publisher>
npx vsce publish

# Open VSX
npx ovsx publish codehub-0.3.0.vsix -p <token>
```

## 3) GitHub Release (recommended)

Attach `codehub-0.3.0.vsix` to a `v0.3.0` GitHub Release so users can download without Marketplace.
