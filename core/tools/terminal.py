"""Terminal tool with workspace cwd and basic safety limits."""

from __future__ import annotations

import asyncio
import shlex

from .filesystem import WorkspaceSandbox

# Block obviously destructive / privilege-escalating patterns for V0.1.
_BLOCKED_PATTERNS = (
    "rm -rf /",
    "mkfs",
    ":(){",
    "shutdown",
    "reboot",
    "sudo ",
    "dd if=",
)


async def run_terminal(
    sandbox: WorkspaceSandbox,
    command: str,
    *,
    timeout_seconds: float = 60.0,
    max_output_chars: int = 30_000,
) -> str:
    cleaned = command.strip()
    if not cleaned:
        return "ERROR: empty command"

    lowered = cleaned.lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in lowered:
            return f"ERROR: blocked command pattern: {pattern!r}"

    try:
        proc = await asyncio.create_subprocess_shell(
            cleaned,
            cwd=str(sandbox.root),
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
            return f"ERROR: command timed out after {timeout_seconds}s"
    except OSError as exc:
        return f"ERROR: failed to start command: {exc}"

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    output_parts = [
        f"exit_code={proc.returncode}",
        f"cwd={sandbox.root}",
        f"cmd={shlex.quote(cleaned)}",
    ]
    if stdout:
        output_parts.append("--- stdout ---\n" + stdout)
    if stderr:
        output_parts.append("--- stderr ---\n" + stderr)
    text = "\n".join(output_parts)
    if len(text) > max_output_chars:
        return text[:max_output_chars] + f"\n...[truncated, total {len(text)} chars]"
    return text
