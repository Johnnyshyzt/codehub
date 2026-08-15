# CodeHub — One Agent. Every Model.

开源、多模型、智能路由的 AI Coding Agent 平台。

> 让开发者不再需要选择 AI 模型。  
> CodeHub 自动为当前任务选择最合适的模型，并在限流或失败时无缝切换。

**仓库**：https://github.com/Johnnyshyzt/codehub

---

## 当前状态

**Phase B+ / Git tools**

- [x] OpenAI-compatible Provider（DeepSeek / Qwen / GLM / Kimi）
- [x] Smart Router + 自动 Fallback（429 / 5xx / timeout）
- [x] Agent Runtime（multi-step tool loop）
- [x] Tools：`read_file` / `write_file` / `list_dir` / `run_terminal` / `grep` / `search_files`
- [x] Git 工具：`git_status` / `git_diff` / `git_log` / `git_commit`（需 confirm）
- [x] 最小 Context Engine（文件树 + 打开文件/选区）
- [x] CLI：`codehub ask` / `codehub models` / `codehub serve`
- [x] 本地 HTTP API（`/v1/run` + SSE stream + token 事件）
- [x] VS Code Extension（Chat + Diff + Keep/Revert + 流式 + Cancel + 启动引导）
- [ ] MCP
- [ ] Quota Manager / Benchmark

---

## 快速开始

```bash
git clone https://github.com/Johnnyshyzt/codehub.git
cd codehub

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
# 建议 Python 3.10+（当前兼容 3.9+）

# 配置至少一个模型 Key
cp .env.example .env
# 编辑 .env，例如填入 DEEPSEEK_API_KEY=sk-...

# 查看可用模型
codehub models

# 在当前目录跑一个 coding 任务
codehub ask "列出这个仓库的顶层结构，并总结 README 在说什么"

# 或跑端到端 demo（会在临时目录写文件并跑 pytest）
python -m examples.coding_task

# 启动本地 API（给 VS Code 扩展用）
codehub serve
```

### VS Code 扩展

```bash
cd apps/vscode
npm install
npm run compile
```

然后用 Cursor/VS Code 打开本仓库，按 `apps/vscode/README.md` 用 F5 跑扩展，或配置 API Key 后打开侧边栏 **CodeHub** 面板。

### 环境变量（BYOK）

| Provider | Env |
|----------|-----|
| DeepSeek | `DEEPSEEK_API_KEY` |
| Qwen | `DASHSCOPE_API_KEY` 或 `QWEN_API_KEY` |
| GLM | `ZHIPU_API_KEY` 或 `GLM_API_KEY` |
| Kimi | `MOONSHOT_API_KEY` 或 `KIMI_API_KEY` |

---

## 核心理念

| 原则 | 说明 |
|------|------|
| **Open Source** | 核心 Agent + Router + Provider 层开源 |
| **Model Neutral** | 不绑定任何单一大模型厂商 |
| **Smart Router** | 根据任务类型、能力、成本自动选择模型 |
| **Free First** | 早期合法使用各厂商官方免费额度 + BYOK |
| **Local-first** | 工具默认只在本地 workspace 沙箱内读写 |

---

## 项目结构

```text
codehub/
├── codehub/            # CLI + local HTTP server
├── providers/          # 模型厂商适配（OpenAI-compatible）
├── core/
│   ├── agent/          # Agent Runtime（tool loop）
│   ├── router/         # Smart Router + Fallback
│   ├── tools/          # filesystem / terminal
│   ├── config.py
│   └── factory.py
├── apps/
│   └── vscode/         # VS Code / Cursor 扩展
├── examples/
└── tests/
```

---

## 路线图

**V0.1** — 能用：真实 Provider + Router/Fallback + Agent tools + CLI ✅  
**V0.1b** — VS Code Extension + local API ✅  
**V0.2** — Context / grep / Git tools / Keep-Revert / token stream ✅ → 下一步 MCP / Quota  
**V0.3** — Model Score / Benchmark / Quota  
**V1.0** — Developer Platform  

---

## 开发

```bash
pytest -q
ruff check .
```

---

## License

Apache License 2.0

---

**One Agent. Every Model.**
