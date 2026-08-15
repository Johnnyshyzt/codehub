# CodeHub Architecture (V0.3)

## High-level Goal

**One Agent. Every Model.**

CodeHub is an open-source AI Coding Agent platform that does **not** bind to any single model vendor.
It provides a unified Agent runtime + Smart Model Router + automatic fallback so developers no longer need to manually choose which model to use.

## Runtime Flow

```
Developer (CLI / VS Code)
        ↓
   Local HTTP API (optional)  ← FastAPI :8765 / SSE
        ↓
   Agent Runtime              ← multi-step tool loop + file change tracking
        ↓
   Smart Router               ← task type + capabilities + ranking
        ↓
   chat_with_fallback         ← 429 / timeout / 5xx → next provider
        ↓
   Provider Abstraction (OpenAI-compatible)
        ├── DeepSeek
        ├── Qwen
        ├── GLM
        └── Kimi
        ↓
   Tools (workspace sandbox + optional MCP)
        ├── list_dir / read_file / write_file
        ├── grep / search_files
        ├── git_status / git_diff / git_log / git_commit
        ├── run_terminal
        └── mcp__<server>__<tool>   ← selective MCP
```

## Key Design Principles

1. **Model Neutral** — Agent never imports a concrete vendor SDK; everything goes through `BaseProvider` / `OpenAICompatibleProvider`.
2. **Local-first** — Tools are confined to a workspace root; no full-repo upload service in V0.1.
3. **BYOK** — API keys come from environment / `.env`.
4. **Progressive enhancement** — Rule-based router now; score/benchmark-driven router later.
5. **Git safety** — commit requires `confirm=true`; no amend / push / hook-skip from the tool.
6. **Streaming** — Router streams completions, Agent emits `token` SSE events for the UI.
7. **Selective MCP** — Opt-in via `.codehub/mcp.json` + tool allow-list; SDK is an optional extra.

## Module Map

| Path | Responsibility |
|------|----------------|
| `core/context/` | Shallow file tree + editor hints |
| `core/benchmark/` | Model scores + routing bonus |
| `core/mcp/` | Selective MCP client (stdio) + tool bridge |
| `core/quota/` | Local token usage store (`~/.codehub/usage.json`) |
| `core/tools/` | Sandboxed filesystem, terminal, grep/search, git |
| `codehub/cli.py` | `ask` / `models` / `usage` / `scores` / `mcp` / `serve` |
| `codehub/server.py` | HTTP + SSE + `/v1/usage` + `/v1/scores` + `/v1/mcp` |
| `apps/vscode/` | Chat + Diff + Keep/Revert + streaming + status telemetry |

## Next Steps

1. Richer offline benchmark suite (coding tasks corpus)
2. Keep MCP sessions warm across tool calls (perf)
3. Publish VSIX / install docs
