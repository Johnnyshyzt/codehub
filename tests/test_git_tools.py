"""Git tool tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.tools.filesystem import WorkspaceSandbox
from core.tools.git import git_commit, git_diff, git_log, git_status
from core.tools.registry import ToolRegistry


def _init_repo(root: Path) -> None:
    # Empty template avoids writing sample hooks (some sandboxes block that).
    subprocess.run(
        ["git", "init", "--template="],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.mark.asyncio
async def test_git_tools_not_a_repo(tmp_path: Path) -> None:
    sandbox = WorkspaceSandbox(tmp_path)
    status = await git_status(sandbox)
    assert status.startswith("ERROR: not a git repository")


@pytest.mark.asyncio
async def test_git_status_diff_log(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sandbox = WorkspaceSandbox(tmp_path)

    status = await git_status(sandbox)
    assert not status.startswith("ERROR:")
    assert "##" in status or "main" in status or "master" in status

    (tmp_path / "README.md").write_text("hello\nworld\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("x\n", encoding="utf-8")

    status2 = await git_status(sandbox)
    assert "README.md" in status2
    assert "new.txt" in status2

    diff = await git_diff(sandbox)
    assert "world" in diff or "+world" in diff

    path_diff = await git_diff(sandbox, path="README.md")
    assert "README.md" in path_diff or "world" in path_diff

    log = await git_log(sandbox, max_count=5)
    assert "initial" in log


@pytest.mark.asyncio
async def test_git_diff_staged(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sandbox = WorkspaceSandbox(tmp_path)
    (tmp_path / "staged.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=tmp_path, check=True, capture_output=True)

    staged = await git_diff(sandbox, staged=True)
    assert "staged" in staged

    unstaged = await git_diff(sandbox, staged=False)
    assert unstaged == "(empty)" or "staged" not in unstaged


@pytest.mark.asyncio
async def test_git_tools_via_registry(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    registry = ToolRegistry(WorkspaceSandbox(tmp_path))
    names = {t["function"]["name"] for t in registry.openai_tools()}
    assert {"git_status", "git_diff", "git_log", "git_commit"} <= names

    out = await registry.execute("git_log", '{"max_count": 3}')
    assert "initial" in out


@pytest.mark.asyncio
async def test_git_commit_requires_confirm(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sandbox = WorkspaceSandbox(tmp_path)
    (tmp_path / "README.md").write_text("hello\nworld\n", encoding="utf-8")
    out = await git_commit(sandbox, message="update", confirm=False)
    assert "confirm=true" in out


@pytest.mark.asyncio
async def test_git_commit_success(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sandbox = WorkspaceSandbox(tmp_path)
    (tmp_path / "README.md").write_text("hello\nworld\n", encoding="utf-8")
    out = await git_commit(
        sandbox,
        message="update readme",
        confirm=True,
        paths=["README.md"],
    )
    assert not out.startswith("ERROR:"), out
    log = await git_log(sandbox, max_count=3)
    assert "update readme" in log
