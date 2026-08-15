"""Read-only Git tools scoped to the workspace root."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from .filesystem import WorkspaceSandbox

_MAX_OUTPUT = 40_000


def _find_git_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


async def _run_git(
    sandbox: WorkspaceSandbox,
    args: list[str],
    *,
    timeout_seconds: float = 30.0,
    max_output_chars: int = _MAX_OUTPUT,
) -> str:
    if shutil.which("git") is None:
        return "ERROR: git is not installed or not on PATH"

    root = _find_git_root(sandbox.root)
    if root is None:
        return "ERROR: not a git repository (no .git found from workspace root)"

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"ERROR: git timed out after {timeout_seconds}s"
    except OSError as exc:
        return f"ERROR: failed to run git: {exc}"

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        detail = (stderr or stdout or "unknown error").strip()
        return f"ERROR: git {' '.join(args)} failed (exit {proc.returncode}): {detail}"

    text = stdout if stdout.strip() else "(empty)"
    if len(text) > max_output_chars:
        return text[:max_output_chars] + f"\n...[truncated, total {len(text)} chars]"
    return text


async def git_status(sandbox: WorkspaceSandbox) -> str:
    """Show concise working-tree status (branch, staged, unstaged, untracked)."""
    return await _run_git(
        sandbox,
        ["status", "--short", "--branch"],
    )


async def git_diff(
    sandbox: WorkspaceSandbox,
    *,
    path: str | None = None,
    staged: bool = False,
) -> str:
    """Show unstaged (or staged) diff; optionally limit to a workspace-relative path."""
    args = ["diff", "--no-color"]
    if staged:
        args.append("--cached")
    if path:
        # Validate path stays in workspace, then pass as relative to git root.
        target = sandbox.resolve(path)
        root = _find_git_root(sandbox.root)
        if root is None:
            return "ERROR: not a git repository (no .git found from workspace root)"
        try:
            rel = target.relative_to(root)
        except ValueError:
            return f"ERROR: path is outside git root: {path}"
        args.extend(["--", str(rel)])
    return await _run_git(sandbox, args)


async def git_log(
    sandbox: WorkspaceSandbox,
    *,
    max_count: int = 10,
) -> str:
    """Show recent commits (one line each)."""
    count = max(1, min(int(max_count), 50))
    return await _run_git(
        sandbox,
        [
            "log",
            f"-n{count}",
            "--oneline",
            "--decorate",
            "--no-color",
        ],
    )


_BLOCKED_MESSAGE_SNIPPETS = (
    "--amend",
    "--no-verify",
    "-n ",
    "\n-n",
)


async def git_commit(
    sandbox: WorkspaceSandbox,
    *,
    message: str,
    confirm: bool = False,
    paths: list[str] | None = None,
) -> str:
    """
    Stage selected (or all tracked) changes and create a commit.

    Safety:
    - confirm must be true
    - message required; no amend / no-verify / force
    - does not push
    """
    if not confirm:
        return "ERROR: git_commit requires confirm=true (user must clearly ask to commit)"

    cleaned = (message or "").strip()
    if not cleaned:
        return "ERROR: commit message is required"
    if len(cleaned) > 2000:
        return "ERROR: commit message too long (max 2000 chars)"
    lowered = cleaned.lower()
    for snippet in _BLOCKED_MESSAGE_SNIPPETS:
        if snippet in lowered:
            return f"ERROR: commit message contains blocked snippet: {snippet!r}"

    # Stage files first.
    if paths:
        for rel in paths:
            if not rel or not str(rel).strip():
                return "ERROR: empty path in paths"
            # Ensure path is inside workspace.
            sandbox.resolve(rel)
        add_args = ["add", "--", *[str(p).strip() for p in paths]]
    else:
        # Tracked modifications/deletes only — does not add brand-new untracked files.
        add_args = ["add", "-u"]

    add_result = await _run_git(sandbox, add_args)
    if add_result.startswith("ERROR:"):
        return add_result

    # Nothing to commit?
    status = await _run_git(sandbox, ["status", "--porcelain"])
    if status.startswith("ERROR:"):
        return status
    if status == "(empty)":
        return "ERROR: nothing to commit (working tree clean after staging)"

    # staged entries start with a non-space in first column, or second for unstaged-only
    has_staged = any(
        line and line[0] not in (" ", "?")
        for line in status.splitlines()
        if line.strip()
    )
    if not has_staged:
        return (
            "ERROR: nothing staged to commit. "
            "Pass paths= to include new files, or ensure there are tracked changes."
        )

    return await _run_git(
        sandbox,
        ["commit", "-m", cleaned],
    )
