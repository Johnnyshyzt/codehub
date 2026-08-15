"""Minimal workspace context engine for V0.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from core.tools.filesystem import WorkspaceSandbox

SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "out",
    ".idea",
    ".vscode",
    "coverage",
    ".tox",
    ".eggs",
}

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".css",
    ".html",
    ".sh",
    ".env",
    ".example",
}


@dataclass
class EditorFileHint:
    path: str
    content: Optional[str] = None
    selection: Optional[str] = None
    language: Optional[str] = None


@dataclass
class ContextBundle:
    workspace_root: str
    file_tree: str
    open_files: List[EditorFileHint] = field(default_factory=list)
    active_file: Optional[EditorFileHint] = None
    notes: List[str] = field(default_factory=list)

    def render(self, *, max_chars: int = 24_000) -> str:
        parts: List[str] = [
            "## Workspace Context",
            f"Root: {self.workspace_root}",
            "",
            "### File tree (shallow)",
            self.file_tree or "(empty)",
        ]

        active = self.active_file
        if active and active.path:
            parts.extend(["", f"### Active file: {active.path}"])
            if active.language:
                parts.append(f"Language: {active.language}")
            if active.selection:
                parts.extend(
                    [
                        "Selected code:",
                        "```",
                        _truncate(active.selection, 6_000),
                        "```",
                    ]
                )
            elif active.content:
                parts.extend(
                    [
                        "File preview:",
                        "```",
                        _truncate(active.content, 8_000),
                        "```",
                    ]
                )

        others = [
            f
            for f in self.open_files
            if not active or f.path != active.path
        ][:4]
        if others:
            parts.extend(["", "### Other open files"])
            for f in others:
                preview = ""
                if f.selection:
                    preview = _truncate(f.selection, 1_500)
                elif f.content:
                    preview = _truncate(f.content, 1_500)
                parts.append(f"- {f.path}")
                if preview:
                    parts.extend(["```", preview, "```"])

        if self.notes:
            parts.extend(["", "### Notes"])
            parts.extend(f"- {n}" for n in self.notes)

        text = "\n".join(parts)
        return _truncate(text, max_chars)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "file_tree": self.file_tree,
            "active_file": _hint_to_dict(self.active_file),
            "open_files": [_hint_to_dict(f) for f in self.open_files],
            "notes": list(self.notes),
        }


def _hint_to_dict(hint: Optional[EditorFileHint]) -> Optional[Dict[str, Any]]:
    if hint is None:
        return None
    return {
        "path": hint.path,
        "content": hint.content,
        "selection": hint.selection,
        "language": hint.language,
    }


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[truncated, total {len(text)} chars]"


def build_file_tree(
    sandbox: WorkspaceSandbox,
    *,
    max_depth: int = 2,
    max_entries: int = 120,
) -> str:
    lines: List[str] = []
    count = 0

    def walk(current: Path, prefix: str, depth: int) -> None:
        nonlocal count
        if count >= max_entries or depth > max_depth:
            return
        try:
            children = sorted(
                current.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError:
            return

        visible = []
        for child in children:
            if child.name in SKIP_DIR_NAMES:
                continue
            if child.name.startswith(".") and child.name not in {".env.example"}:
                continue
            visible.append(child)

        for idx, child in enumerate(visible):
            if count >= max_entries:
                lines.append(f"{prefix}...[truncated]")
                return
            connector = "└── " if idx == len(visible) - 1 else "├── "
            name = child.name + ("/" if child.is_dir() else "")
            lines.append(f"{prefix}{connector}{name}")
            count += 1
            if child.is_dir() and depth < max_depth:
                extension = "    " if idx == len(visible) - 1 else "│   "
                walk(child, prefix + extension, depth + 1)

    root_name = sandbox.root.name or str(sandbox.root)
    lines.append(f"{root_name}/")
    walk(sandbox.root, "", 1)
    return "\n".join(lines)


def build_context(
    workspace: str | Path,
    *,
    active_file: Optional[EditorFileHint] = None,
    open_files: Optional[Sequence[EditorFileHint]] = None,
    max_depth: int = 2,
    include_active_from_disk: bool = True,
) -> ContextBundle:
    sandbox = WorkspaceSandbox(workspace)
    tree = build_file_tree(sandbox, max_depth=max_depth)

    active = active_file
    if active and include_active_from_disk and not active.content and not active.selection:
        active = _hydrate_from_disk(sandbox, active)

    hydrated_open: List[EditorFileHint] = []
    for hint in open_files or []:
        if include_active_from_disk and not hint.content and not hint.selection:
            hydrated_open.append(_hydrate_from_disk(sandbox, hint))
        else:
            hydrated_open.append(hint)

    notes = [
        "Use grep/search_files to find symbols before editing unfamiliar files.",
        "Prefer read_file for exact contents; the tree is shallow and may be incomplete.",
        "Use git_status / git_diff / git_log for repository state — do not guess commits.",
    ]
    return ContextBundle(
        workspace_root=str(sandbox.root),
        file_tree=tree,
        open_files=hydrated_open,
        active_file=active,
        notes=notes,
    )


def context_from_payload(
    workspace: str | Path,
    payload: Optional[Dict[str, Any]],
) -> ContextBundle:
    """Build context from API/extension JSON payload."""
    payload = payload or {}
    active_raw = payload.get("active_file")
    open_raw = payload.get("open_files") or []

    active = None
    if isinstance(active_raw, dict) and active_raw.get("path"):
        active = EditorFileHint(
            path=str(active_raw["path"]),
            content=active_raw.get("content"),
            selection=active_raw.get("selection"),
            language=active_raw.get("language"),
        )

    opens: List[EditorFileHint] = []
    if isinstance(open_raw, list):
        for item in open_raw:
            if not isinstance(item, dict) or not item.get("path"):
                continue
            opens.append(
                EditorFileHint(
                    path=str(item["path"]),
                    content=item.get("content"),
                    selection=item.get("selection"),
                    language=item.get("language"),
                )
            )

    return build_context(
        workspace,
        active_file=active,
        open_files=opens,
        max_depth=int(payload.get("max_depth") or 2),
    )


def _hydrate_from_disk(sandbox: WorkspaceSandbox, hint: EditorFileHint) -> EditorFileHint:
    try:
        target = sandbox.resolve(hint.path)
    except PermissionError:
        return hint
    if not target.is_file():
        return hint
    if target.suffix.lower() not in TEXT_SUFFIXES and target.suffix != "":
        return hint
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hint
    return EditorFileHint(
        path=hint.path,
        content=_truncate(content, 8_000),
        selection=hint.selection,
        language=hint.language,
    )
