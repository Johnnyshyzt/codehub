"""
End-to-end coding agent demo with tools.

Creates a tiny scratch project under /tmp (or --workspace), then asks the
agent to implement a function and verify it.

Usage:
    export DEEPSEEK_API_KEY=sk-...
    python -m examples.coding_task
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rich.console import Console

from core.factory import create_agent

console = Console()

STARTER_MAIN = '''\
"""Scratch project for CodeHub coding_task demo."""


def add(a: int, b: int) -> int:
    """TODO: implement addition."""
    raise NotImplementedError


if __name__ == "__main__":
    print(add(2, 3))
'''

STARTER_TEST = '''\
from main import add


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
'''


def _print_event(event_type: str, payload: dict) -> None:
    if event_type == "model_response":
        console.print(
            f"[cyan]→[/cyan] {payload.get('provider')}/{payload.get('model')} "
            f"step={payload.get('step')} tools={payload.get('has_tool_calls')}"
        )
    elif event_type == "tool_result":
        preview = (payload.get("preview") or "").replace("\n", " ")[:100]
        console.print(f"[yellow]⚙[/yellow] {payload.get('tool')}: {preview}")


async def main(workspace: Path) -> None:
    (workspace / "main.py").write_text(STARTER_MAIN, encoding="utf-8")
    (workspace / "test_main.py").write_text(STARTER_TEST, encoding="utf-8")

    console.print(f"[bold]Workspace:[/bold] {workspace}")
    agent = create_agent(workspace=workspace, max_steps=10, on_event=_print_event)
    await agent.router.refresh_models()

    prompt = (
        "Implement add() in main.py so the tests pass. "
        "Use tools to edit the file, then run: python -m pytest -q"
    )
    result = await agent.run(prompt, task_type="coding")

    console.print(
        f"\n[bold green]Finished[/bold green] via {result.provider}/{result.model} "
        f"| steps={result.steps} tool_calls={result.tool_calls}"
    )
    console.print(result.content)

    console.print("\n[bold]main.py after agent:[/bold]")
    console.print((workspace / "main.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Existing workspace dir (default: temp dir)",
    )
    args = parser.parse_args()

    if args.workspace:
        args.workspace.mkdir(parents=True, exist_ok=True)
        asyncio.run(main(args.workspace.resolve()))
    else:
        with tempfile.TemporaryDirectory(prefix="codehub-demo-") as tmp:
            asyncio.run(main(Path(tmp)))
