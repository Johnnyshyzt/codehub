"""Text search tools over the workspace sandbox."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional

from .filesystem import WorkspaceSandbox

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
}

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".bz2",
    ".xz",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".a",
    ".wasm",
}


def _iter_files(
    root: Path,
    *,
    glob: Optional[str] = None,
    max_files: int = 2_000,
) -> Iterable[Path]:
    count = 0
    if glob:
        iterator = root.rglob(glob)
    else:
        iterator = root.rglob("*")

    for path in iterator:
        if count >= max_files:
            break
        if not path.is_file():
            continue
        # Skip ignored directories in path parts.
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        count += 1
        yield path


def grep_workspace(
    sandbox: WorkspaceSandbox,
    pattern: str,
    *,
    path: str = ".",
    glob: Optional[str] = None,
    case_insensitive: bool = False,
    max_matches: int = 50,
    context_lines: int = 0,
) -> str:
    """Search file contents with a regex pattern."""
    if not pattern:
        return "ERROR: empty pattern"

    try:
        flags = re.IGNORECASE if case_insensitive else 0
        regex = re.compile(pattern, flags)
    except re.error as exc:
        return f"ERROR: invalid regex: {exc}"

    try:
        base = sandbox.resolve(path)
    except PermissionError as exc:
        return f"ERROR: {exc}"

    if not base.exists():
        return f"ERROR: path not found: {path}"

    search_root = base if base.is_dir() else base.parent
    single_file = base if base.is_file() else None

    matches: List[str] = []
    files_scanned = 0

    files: Iterable[Path]
    if single_file is not None:
        files = [single_file]
    else:
        files = _iter_files(search_root, glob=glob)

    for file_path in files:
        files_scanned += 1
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Skip huge files.
        if len(text) > 1_500_000:
            continue

        lines = text.splitlines()
        rel = str(file_path.relative_to(sandbox.root))
        for idx, line in enumerate(lines):
            if not regex.search(line):
                continue
            line_no = idx + 1
            block = [f"{rel}:{line_no}: {line}"]
            if context_lines > 0:
                start = max(0, idx - context_lines)
                end = min(len(lines), idx + context_lines + 1)
                for j in range(start, end):
                    if j == idx:
                        continue
                    marker = "-" if j < idx else "+"
                    block.append(f"{rel}:{j + 1}{marker} {lines[j]}")
            matches.append("\n".join(block))
            if len(matches) >= max_matches:
                joined = "\n\n".join(matches)
                return (
                    f"Found {len(matches)}+ matches "
                    f"(scanned {files_scanned} files, truncated)\n\n{joined}"
                )

    if not matches:
        return f"No matches for /{pattern}/ (scanned {files_scanned} files)"
    return f"Found {len(matches)} matches (scanned {files_scanned} files)\n\n" + "\n\n".join(
        matches
    )


def search_files(
    sandbox: WorkspaceSandbox,
    query: str,
    *,
    path: str = ".",
    max_results: int = 50,
) -> str:
    """Find file paths whose names contain the query (case-insensitive)."""
    q = (query or "").strip().lower()
    if not q:
        return "ERROR: empty query"

    try:
        base = sandbox.resolve(path)
    except PermissionError as exc:
        return f"ERROR: {exc}"
    if not base.exists():
        return f"ERROR: path not found: {path}"
    if not base.is_dir():
        return f"ERROR: not a directory: {path}"

    hits: List[str] = []
    for file_path in _iter_files(base):
        rel = str(file_path.relative_to(sandbox.root))
        if q in file_path.name.lower() or q in rel.lower():
            hits.append(rel)
            if len(hits) >= max_results:
                break

    if not hits:
        return f"No file paths matching {query!r}"
    return f"Found {len(hits)} paths:\n" + "\n".join(f"- {h}" for h in hits)
