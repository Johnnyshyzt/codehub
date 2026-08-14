"""Workspace-scoped filesystem tools for the coding agent."""

from __future__ import annotations

from pathlib import Path


class WorkspaceSandbox:
    """Resolve and validate paths so tools cannot escape the workspace root."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"Workspace root does not exist: {self.root}")

    def resolve(self, relative_path: str) -> Path:
        # Treat absolute paths as relative to root for safety.
        candidate = Path(relative_path)
        if candidate.is_absolute():
            target = candidate.resolve()
        else:
            target = (self.root / candidate).resolve()

        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise PermissionError(
                f"Path escapes workspace: {relative_path} (root={self.root})"
            ) from exc
        return target


def read_file(sandbox: WorkspaceSandbox, path: str, max_chars: int = 100_000) -> str:
    target = sandbox.resolve(path)
    if not target.exists():
        return f"ERROR: file not found: {path}"
    if not target.is_file():
        return f"ERROR: not a file: {path}"
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n...[truncated, total {len(text)} chars]"
    return text


def write_file(sandbox: WorkspaceSandbox, path: str, content: str) -> str:
    target = sandbox.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: wrote {len(content)} chars to {path}"


def list_dir(
    sandbox: WorkspaceSandbox,
    path: str = ".",
    max_entries: int = 200,
) -> str:
    target = sandbox.resolve(path)
    if not target.exists():
        return f"ERROR: directory not found: {path}"
    if not target.is_dir():
        return f"ERROR: not a directory: {path}"

    entries: list[str] = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name.startswith(".") and child.name not in {".env.example"}:
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(f"{child.name}{suffix}")
        if len(entries) >= max_entries:
            entries.append(f"...[{max_entries}+ entries, truncated]")
            break
    if not entries:
        return "(empty)"
    return "\n".join(entries)
