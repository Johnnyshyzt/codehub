"""Filesystem / terminal tool tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.tools.filesystem import WorkspaceSandbox, list_dir, read_file, write_file
from core.tools.registry import ToolRegistry
from core.tools.terminal import run_terminal


def test_sandbox_blocks_escape(tmp_path: Path) -> None:
    sandbox = WorkspaceSandbox(tmp_path)
    with pytest.raises(PermissionError):
        sandbox.resolve("../outside.txt")


def test_read_write_list(tmp_path: Path) -> None:
    sandbox = WorkspaceSandbox(tmp_path)
    assert "OK" in write_file(sandbox, "hello.txt", "world")
    assert read_file(sandbox, "hello.txt") == "world"
    listing = list_dir(sandbox, ".")
    assert "hello.txt" in listing


@pytest.mark.asyncio
async def test_run_terminal(tmp_path: Path) -> None:
    sandbox = WorkspaceSandbox(tmp_path)
    out = await run_terminal(sandbox, "echo hi")
    assert "exit_code=0" in out
    assert "hi" in out


@pytest.mark.asyncio
async def test_tool_registry_execute(tmp_path: Path) -> None:
    registry = ToolRegistry(WorkspaceSandbox(tmp_path))
    result = await registry.execute(
        "write_file",
        '{"path": "a.py", "content": "print(1)"}',
    )
    assert result.startswith("OK")
    read_back = await registry.execute("read_file", '{"path": "a.py"}')
    assert read_back == "print(1)"
