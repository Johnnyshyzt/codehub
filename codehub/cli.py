"""CodeHub CLI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from core.config import configured_provider_names, load_env, missing_key_help
from core.factory import build_run_context, create_agent

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
        await agent.router.refresh_models()
        context_text = None
        if not no_tools:
            root = workspace or Path.cwd()
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

    try:
        asyncio.run(_run())
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


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
            "[bold]codehub serve[/bold]"
        )


if __name__ == "__main__":
    app()
