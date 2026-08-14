"""
Minimal chat example (no tools).

Usage:
    export DEEPSEEK_API_KEY=sk-...
    python -m examples.simple_agent
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rich.console import Console

from core.factory import create_agent

console = Console()


async def main() -> None:
    console.print("[bold]CodeHub — simple chat (no tools)[/bold]")
    agent = create_agent(with_tools=False)
    await agent.router.refresh_models()

    console.print("\nAvailable models:")
    for m in agent.router.list_available_models():
        console.print(f"  - {m.provider}/{m.id}")

    result = await agent.run(
        user_input="Write a Python function that calculates fibonacci numbers. Be concise.",
        task_type="simple_edit",
        system_prompt="You are a helpful coding assistant. Be concise and correct.",
    )
    console.print(f"\n[{result.provider}/{result.model}]")
    console.print(result.content)


if __name__ == "__main__":
    asyncio.run(main())
