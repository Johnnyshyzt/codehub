# Changelog

All notable changes to CodeHub are documented here.

## [0.3.0] — 2026-08-15

### Added
- Local quota / usage (`codehub usage`, `/v1/usage`)
- Selective MCP tools with warm session pool (per-run CLI + cross-request `serve`)
- Model scores + Smart Router bonus (`codehub scores`)
- Offline / live / matrix benchmark suite (`codehub bench`, 8 tasks)
- VS Code extension VSIX packaging (`npm run package` → `0.3.0`)
- GitHub Actions CI (pytest, ruff, mock bench, VSIX compile)
- Optional nightly live matrix workflow (manual / schedule + secrets)
- `codehub version` / `codehub -V`

### Changed
- Diff snapshots stored in memory (large-file friendly)
- README / architecture marked V0.3 (local-complete; publish when ready)

## [0.2.0] — prior

- Git tools, Keep/Revert, token streaming, Cancel, startup guidance

## [0.1.0] — prior

- Multi-provider Agent, Smart Router, CLI, local HTTP API, VS Code chat MVP
