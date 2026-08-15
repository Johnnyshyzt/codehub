"""CodeHub CLI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from core.config import configured_provider_names, load_env, missing_key_help
from core.factory import (
    attach_configured_mcp,
    build_run_context,
    close_configured_mcp,
    create_agent,
)

app = typer.Typer(
    name="codehub",
    help="CodeHub — One Agent. Every Model.",
    add_completion=False,
)
console = Console()


def _print_event(event_type: str, payload: dict) -> None:
    if event_type == "model_response":
        console.print(
            f"[cyan]→[/cyan] step {payload.get('step')} "
            f"{payload.get('provider')}/{payload.get('model')} "
            f"(tools={payload.get('has_tool_calls')})"
        )
    elif event_type == "tool_result":
        preview = (payload.get("preview") or "").replace("\n", " ")
        console.print(f"[yellow]⚙[/yellow] {payload.get('tool')}: {preview[:120]}")


@app.command("models")
def models_cmd() -> None:
    """List configured providers / models."""
    load_env()
    names = configured_provider_names()
    if not names:
        console.print(missing_key_help())
        raise typer.Exit(code=1)

    async def _run() -> None:
        agent = create_agent(with_tools=False)
        await agent.router.refresh_models()
        console.print("[bold]Configured providers:[/bold]", ", ".join(names))
        for m in agent.router.list_available_models():
            caps = ", ".join(c.value for c in m.capabilities)
            console.print(f"  - {m.provider}/{m.id}  ({caps})")

    asyncio.run(_run())


@app.command("ask")
def ask_cmd(
    prompt: str = typer.Argument(..., help="Task for the coding agent"),
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace root (default: cwd)"
    ),
    task_type: str = typer.Option("coding", "--task-type", "-t"),
    max_steps: int = typer.Option(12, "--max-steps"),
    no_tools: bool = typer.Option(False, "--no-tools", help="Disable tool calling"),
) -> None:
    """Run a coding task with Smart Router + tools."""

    async def _run() -> None:
        agent = create_agent(
            workspace=workspace,
            max_steps=max_steps,
            with_tools=not no_tools,
            on_event=_print_event,
        )
        root = workspace or Path.cwd()
        try:
            if not no_tools:
                attached = await attach_configured_mcp(agent, root)
                if attached.tool_names:
                    console.print(
                        f"[cyan]MCP tools:[/cyan] {', '.join(attached.tool_names)}"
                    )
            await agent.router.refresh_models()
            context_text = None
            if not no_tools:
                context_text = build_run_context(root).render()
            console.print(
                Panel.fit(
                    prompt,
                    title="CodeHub Task",
                    border_style="green",
                )
            )
            result = await agent.run(prompt, task_type=task_type, context_text=context_text)
            console.print()
            console.print(
                f"[bold green]Done[/bold green] via {result.provider}/{result.model} "
                f"| steps={result.steps} tools={result.tool_calls} "
                f"tokens≈{result.usage_total_tokens}"
            )
            console.print(Panel(result.content or "(empty)", title="Result", border_style="blue"))
        finally:
            await close_configured_mcp(agent)

    try:
        asyncio.run(_run())
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("bench")
def bench_cmd(
    live: bool = typer.Option(
        False,
        "--live",
        help="Use configured live providers (needs API keys). Default is mock/offline.",
    ),
    update_scores: bool = typer.Option(
        True,
        "--update-scores/--no-update-scores",
        help="Write outcomes into local model_scores.json (live mode).",
    ),
    max_steps: int = typer.Option(10, "--max-steps"),
) -> None:
    """Run the built-in coding benchmark suite."""
    from core.benchmark import run_benchmark

    async def _run():
        return await run_benchmark(
            mock=not live,
            update_scores=update_scores and live,
            max_steps=max_steps,
        )

    console.print(
        f"[bold]CodeHub bench[/bold] mode={'live' if live else 'mock/offline'}"
    )
    try:
        report = asyncio.run(_run())
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    for item in report.results:
        mark = "[green]PASS[/green]" if item.passed else "[red]FAIL[/red]"
        console.print(
            f"  {mark} {item.task_id}: {item.detail} "
            f"({item.latency_ms:.0f}ms steps={item.steps} tools={item.tool_calls})"
        )
    console.print(
        f"\n[bold]Result[/bold] {report.passed}/{report.total} passed "
        f"({report.pass_rate:.0%}) quality≈{report.quality}"
    )
    if report.failed:
        raise typer.Exit(code=1)


@app.command("scores")
def scores_cmd(
    set_score: Optional[str] = typer.Option(
        None,
        "--set",
        help="Set quality score: provider/model=0-100 (e.g. deepseek/deepseek-chat=85)",
    ),
    reset: bool = typer.Option(False, "--reset", help="Clear stored model scores"),
    path: Optional[Path] = typer.Option(
        None, "--path", help="Scores JSON path (default: ~/.codehub/model_scores.json)"
    ),
) -> None:
    """Show or update local model scores used by Smart Router."""
    from core.benchmark import get_score_store

    store = get_score_store(path)
    if reset:
        store.reset()
        console.print(f"[yellow]Scores reset[/yellow] → {store.path}")
        return
    if set_score:
        if "=" not in set_score or "/" not in set_score:
            console.print("[red]Format: provider/model=score[/red]")
            raise typer.Exit(code=1)
        left, raw_score = set_score.rsplit("=", 1)
        provider, model = left.split("/", 1)
        entry = store.set_quality(provider.strip(), model.strip(), float(raw_score))
        console.print(
            f"[green]Set[/green] {provider}/{model} quality={entry.quality} "
            f"(routing_bonus=+{entry.routing_bonus()})"
        )
        return

    data = store.summary()
    console.print(f"[bold]Scores file:[/bold] {data['path']}")
    models = data.get("models") or {}
    if not models:
        console.print("No scores yet. They accumulate from live calls, or use --set.")
        return
    for key, info in models.items():
        console.print(
            f"  {key}: bonus=+{info['routing_bonus']}  "
            f"quality={info.get('quality')}  "
            f"calls={info['calls']}  "
            f"success={info['success_rate']:.0%}  "
            f"latency≈{info['avg_latency_ms']:.0f}ms"
        )


@app.command("mcp")
def mcp_cmd(
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace root for .codehub/mcp.json"
    ),
) -> None:
    """List configured MCP servers / discoverable tools."""
    from core.mcp import load_mcp_config, mcp_sdk_available
    from core.mcp.client import list_server_tools
    from core.mcp.config import mcp_tool_name

    root = workspace or Path.cwd()
    config = load_mcp_config(root)
    if not config.enabled_servers:
        console.print(
            "No MCP servers configured.\n"
            "Create `.codehub/mcp.json` (see `.codehub/mcp.example.json`) "
            "or set CODEHUB_MCP_CONFIG."
        )
        raise typer.Exit(code=0)

    console.print(f"[bold]SDK installed:[/bold] {mcp_sdk_available()}")
    for server in config.enabled_servers:
        console.print(
            f"[bold]{server.name}[/bold]: {server.command} {' '.join(server.args)}"
        )
        if not mcp_sdk_available():
            console.print("  (install mcp: pip install 'codehub[mcp]')")
            continue

        async def _list(s=server):
            return await list_server_tools(s)

        try:
            tools = asyncio.run(_list())
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]error:[/red] {exc}")
            continue
        if not tools:
            console.print("  (no allow-listed tools)")
            continue
        for tool in tools:
            console.print(
                f"  - {mcp_tool_name(server.name, tool.name)}  ← {tool.name}: "
                f"{tool.description[:80]}"
            )


@app.command("usage")
def usage_cmd(
    reset: bool = typer.Option(False, "--reset", help="Clear stored usage counters"),
    path: Optional[Path] = typer.Option(
        None, "--path", help="Usage JSON path (default: ~/.codehub/usage.json)"
    ),
) -> None:
    """Show local token usage by provider / model."""
    from core.quota import get_usage_store

    store = get_usage_store(path)
    if reset:
        snap = store.reset()
        console.print(f"[yellow]Usage reset[/yellow] → {store.path}")
    else:
        snap = store.load()

    data = snap.to_dict()
    totals = data["totals"]
    console.print(f"[bold]Usage file:[/bold] {store.path}")
    console.print(
        f"totals: calls={totals['calls']}  "
        f"prompt={totals['prompt_tokens']}  "
        f"completion={totals['completion_tokens']}  "
        f"total={totals['total_tokens']}"
    )
    if data["by_provider"]:
        console.print("[bold]By provider[/bold]")
        for name, counters in data["by_provider"].items():
            console.print(
                f"  {name}: calls={counters['calls']} total={counters['total_tokens']}"
            )
    if data["by_model"]:
        console.print("[bold]By model[/bold]")
        for name, counters in data["by_model"].items():
            console.print(
                f"  {name}: calls={counters['calls']} total={counters['total_tokens']}"
            )
    recent = data.get("recent") or []
    if recent:
        console.print("[bold]Recent[/bold] (last 5)")
        for event in recent[-5:]:
            console.print(
                f"  {event['ts']}  {event['provider']}/{event['model']}  "
                f"+{event['total_tokens']}"
            )


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Start local HTTP API for the VS Code extension."""
    import os

    import uvicorn

    load_env()
    os.environ["CODEHUB_HOST"] = host
    os.environ["CODEHUB_PORT"] = str(port)
    console.print(f"[bold]CodeHub server[/bold] http://{host}:{port}")
    uvicorn.run("codehub.server:app", host=host, port=port, reload=False)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print("CodeHub — One Agent. Every Model.")
        console.print(
            "Try: [bold]codehub models[/bold] | "
            "[bold]codehub ask[/bold] | "
            "[bold]codehub usage[/bold] | "
            "[bold]codehub bench[/bold] | "
            "[bold]codehub scores[/bold] | "
            "[bold]codehub mcp[/bold] | "
            "[bold]codehub serve[/bold]"
        )


if __name__ == "__main__":
    app()
