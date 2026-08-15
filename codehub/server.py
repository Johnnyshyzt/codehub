"""Local HTTP API for VS Code / CLI clients."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from core.config import configured_provider_names, load_env, missing_key_help
from core.factory import attach_configured_mcp, build_run_context, create_agent


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    load_env()
    yield


app = FastAPI(title="CodeHub Local Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    prompt: str
    workspace: Optional[str] = None
    task_type: str = "coding"
    max_steps: int = 12
    api_keys: Optional[Dict[str, str]] = None
    context: Optional[Dict[str, Any]] = None


class RunResponse(BaseModel):
    content: str
    provider: str
    model: str
    steps: int
    tool_calls: int
    usage_total_tokens: int
    events: List[Dict[str, Any]] = Field(default_factory=list)
    file_changes: List[Dict[str, Any]] = Field(default_factory=list)


def _apply_api_keys(api_keys: Optional[Dict[str, str]]) -> None:
    if not api_keys:
        return
    mapping = {
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "glm": "ZHIPU_API_KEY",
        "kimi": "MOONSHOT_API_KEY",
        "DEEPSEEK_API_KEY": "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY": "DASHSCOPE_API_KEY",
        "QWEN_API_KEY": "QWEN_API_KEY",
        "ZHIPU_API_KEY": "ZHIPU_API_KEY",
        "GLM_API_KEY": "GLM_API_KEY",
        "MOONSHOT_API_KEY": "MOONSHOT_API_KEY",
        "KIMI_API_KEY": "KIMI_API_KEY",
    }
    for key, value in api_keys.items():
        if not value:
            continue
        env_name = mapping.get(key, key)
        os.environ[env_name] = value


@app.get("/health")
async def health() -> Dict[str, Any]:
    load_env()
    return {
        "ok": True,
        "providers": configured_provider_names(),
    }


@app.get("/v1/usage")
async def get_usage() -> Dict[str, Any]:
    """Return local token usage summary (~/.codehub/usage.json)."""
    from core.quota import get_usage_store

    store = get_usage_store()
    data = store.summary()
    data["path"] = str(store.path)
    return data


@app.post("/v1/usage/reset")
async def reset_usage() -> Dict[str, Any]:
    from core.quota import get_usage_store

    store = get_usage_store()
    snap = store.reset()
    data = snap.to_dict()
    data["path"] = str(store.path)
    return data


@app.get("/v1/mcp")
async def list_mcp() -> Dict[str, Any]:
    """List configured MCP servers and whether the SDK is available."""
    from core.mcp import load_mcp_config, mcp_sdk_available
    from core.mcp.client import list_server_tools
    from core.mcp.config import mcp_tool_name

    workspace = str(Path.cwd())
    config = load_mcp_config(workspace)
    sdk = mcp_sdk_available()
    servers: List[Dict[str, Any]] = []
    for server in config.enabled_servers:
        entry: Dict[str, Any] = {
            "name": server.name,
            "command": server.command,
            "args": server.args,
            "allow_tools": server.allow_tools,
            "tools": [],
        }
        if sdk:
            try:
                tools = await list_server_tools(server)
                entry["tools"] = [
                    {
                        "name": t.name,
                        "openai_name": mcp_tool_name(server.name, t.name),
                        "description": t.description,
                    }
                    for t in tools
                ]
            except Exception as exc:  # noqa: BLE001
                entry["error"] = str(exc)
        servers.append(entry)
    return {"sdk_available": sdk, "servers": servers}


@app.get("/v1/models")
async def list_models() -> Dict[str, Any]:
    load_env()
    names = configured_provider_names()
    if not names:
        raise HTTPException(status_code=400, detail=missing_key_help())
    agent = create_agent(with_tools=False, load_dotenv=True)
    await agent.router.refresh_models()
    models = [
        {
            "id": m.id,
            "provider": m.provider,
            "display_name": m.display_name,
            "capabilities": [c.value for c in m.capabilities],
        }
        for m in agent.router.list_available_models()
    ]
    return {"providers": names, "models": models}


@app.post("/v1/run", response_model=RunResponse)
async def run_agent(body: RunRequest) -> RunResponse:
    _apply_api_keys(body.api_keys)
    load_env()
    workspace = body.workspace or str(Path.cwd())
    try:
        agent = create_agent(
            workspace=workspace,
            max_steps=body.max_steps,
            with_tools=True,
            load_dotenv=True,
        )
        await attach_configured_mcp(agent, workspace)
        await agent.router.refresh_models()
        ctx = build_run_context(workspace, body.context)
        result = await agent.run(
            body.prompt,
            task_type=body.task_type,
            context_text=ctx.render(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RunResponse(
        content=result.content,
        provider=result.provider,
        model=result.model,
        steps=result.steps,
        tool_calls=result.tool_calls,
        usage_total_tokens=result.usage_total_tokens,
        events=result.events,
        file_changes=result.file_changes,
    )


@app.post("/v1/run/stream")
async def run_agent_stream(body: RunRequest) -> EventSourceResponse:
    _apply_api_keys(body.api_keys)
    load_env()
    workspace = body.workspace or str(Path.cwd())
    queue: asyncio.Queue = asyncio.Queue()
    cancelled = asyncio.Event()

    async def on_event(event_type: str, payload: Dict[str, Any]) -> None:
        await queue.put({"type": event_type, "payload": payload})

    async def runner() -> None:
        try:
            agent = create_agent(
                workspace=workspace,
                max_steps=body.max_steps,
                with_tools=True,
                on_event=on_event,
                cancel_check=cancelled.is_set,
                load_dotenv=True,
            )
            await attach_configured_mcp(agent, workspace)
            await agent.router.refresh_models()
            ctx = build_run_context(workspace, body.context)
            result = await agent.run(
                body.prompt,
                task_type=body.task_type,
                context_text=ctx.render(),
            )
            await queue.put(
                {
                    "type": "done",
                    "payload": {
                        "content": result.content,
                        "provider": result.provider,
                        "model": result.model,
                        "steps": result.steps,
                        "tool_calls": result.tool_calls,
                        "usage_total_tokens": result.usage_total_tokens,
                        "events": result.events,
                        "file_changes": result.file_changes,
                    },
                }
            )
        except asyncio.CancelledError:
            await queue.put(
                {"type": "error", "payload": {"message": "Cancelled by user", "cancelled": True}}
            )
            raise
        except Exception as exc:  # noqa: BLE001
            from core.agent.runtime import AgentCancelled

            message = str(exc)
            payload: Dict[str, Any] = {"message": message}
            if isinstance(exc, AgentCancelled) or "Cancelled by user" in message:
                payload["cancelled"] = True
            await queue.put({"type": "error", "payload": payload})
        finally:
            await queue.put(None)

    async def event_generator() -> AsyncIterator[Dict[str, str]]:
        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield {"event": item["type"], "data": json.dumps(item["payload"])}
        except asyncio.CancelledError:
            cancelled.set()
            task.cancel()
            raise
        finally:
            cancelled.set()
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    return EventSourceResponse(event_generator())


def main() -> None:
    import uvicorn

    host = os.getenv("CODEHUB_HOST", "127.0.0.1")
    port = int(os.getenv("CODEHUB_PORT", "8765"))
    uvicorn.run("codehub.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
