"""Context engine + search tool tests."""

from __future__ import annotations

from pathlib import Path

from core.context.workspace import EditorFileHint, build_context, build_file_tree
from core.tools.filesystem import WorkspaceSandbox
from core.tools.search import grep_workspace, search_files


def test_build_file_tree(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "skip.js").write_text("1", encoding="utf-8")

    sandbox = WorkspaceSandbox(tmp_path)
    tree = build_file_tree(sandbox, max_depth=2)
    assert "README.md" in tree
    assert "a/" in tree
    assert "node_modules" not in tree


def test_build_context_includes_active_selection(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("def add(a,b):\n    return a+b\n", encoding="utf-8")
    ctx = build_context(
        tmp_path,
        active_file=EditorFileHint(
            path="main.py",
            selection="def add(a,b):",
            language="python",
        ),
        include_active_from_disk=False,
    )
    text = ctx.render()
    assert "Workspace Context" in text
    assert "main.py" in text
    assert "def add(a,b):" in text


def test_grep_and_search_files(tmp_path: Path) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "router.py").write_text(
        "class SmartRouter:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "readme.txt").write_text("hello SmartRouter\n", encoding="utf-8")
    sandbox = WorkspaceSandbox(tmp_path)

    grepped = grep_workspace(sandbox, r"class SmartRouter", glob="*.py")
    assert "core/router.py" in grepped

    found = search_files(sandbox, "router")
    assert "core/router.py" in found
