# CodeHub Architecture (V0.1)

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
   Tools (workspace sandbox)
        ├── list_dir / read_file / write_file
        └── run_terminal
```

## Key Design Principles

1. **Model Neutral** — Agent never imports a concrete vendor SDK; everything goes through `BaseProvider` / `OpenAICompatibleProvider`.
2. **Local-first** — Tools are confined to a workspace root; no full-repo upload service in V0.1.
3. **BYOK** — API keys come from environment / `.env`.
4. **Progressive enhancement** — Rule-based router now; score/benchmark-driven router later.

## Module Map

| Path | Responsibility |
|------|----------------|
| `core/context/` | Shallow file tree + editor hints |
| `core/tools/` | Sandboxed filesystem, terminal, grep/search |
| `codehub/cli.py` | `codehub ask` / `codehub models` / `codehub serve` |
| `codehub/server.py` | Local HTTP + SSE for VS Code |
| `apps/vscode/` | Chat sidebar + Diff + context payload |

## Next Steps

1. Keep daily-driving the VS Code extension and fix friction
2. MCP (selective)
3. Git tools (diff / commit)
4. Quota / usage telemetry (local)
5. Benchmark-informed router weights
