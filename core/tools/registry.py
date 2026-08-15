"""Tool registry: OpenAI-style schemas + local executors."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Union

from providers.openai_compatible import parse_tool_arguments

from .filesystem import WorkspaceSandbox, list_dir, read_file, write_file
from .git import git_commit, git_diff, git_log, git_status
from .search import grep_workspace, search_files
from .terminal import run_terminal

ToolHandler = Callable[..., Union[Awaitable[str], str]]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


@dataclass
class FileChange:
    path: str
    action: str  # "created" | "modified"
    before: str | None = None
    after: str | None = None


class ToolRegistry:
    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox
        self._tools: dict[str, ToolSpec] = {}
        self.file_changes: list[FileChange] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(
            ToolSpec(
                name="list_dir",
                description="List files and directories under a workspace-relative path.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path. Default: '.'",
                        }
                    },
                    "required": [],
                },
                handler=self._list_dir,
            )
        )
        self.register(
            ToolSpec(
                name="read_file",
                description="Read a text file from the workspace.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Workspace-relative file path.",
                        }
                    },
                    "required": ["path"],
                },
                handler=self._read_file,
            )
        )
        self.register(
            ToolSpec(
                name="write_file",
                description=(
                    "Create or overwrite a text file in the workspace. "
                    "Prefer writing complete file contents."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Workspace-relative file path.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Full file contents to write.",
                        },
                    },
                    "required": ["path", "content"],
                },
                handler=self._write_file,
            )
        )
        self.register(
            ToolSpec(
                name="run_terminal",
                description=(
                    "Run a shell command inside the workspace root. "
                    "Use for tests, linters, and short build commands."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Shell command to execute.",
                        }
                    },
                    "required": ["command"],
                },
                handler=self._run_terminal,
            )
        )
        self.register(
            ToolSpec(
                name="grep",
                description=(
                    "Search file contents with a regex. "
                    "Use to find symbols, strings, or call sites before editing."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Regex pattern to search for.",
                        },
                        "path": {
                            "type": "string",
                            "description": "Workspace-relative file or directory. Default: '.'",
                        },
                        "glob": {
                            "type": "string",
                            "description": "Optional filename glob, e.g. '*.py'.",
                        },
                        "case_insensitive": {
                            "type": "boolean",
                            "description": "Case-insensitive search. Default false.",
                        },
                        "max_matches": {
                            "type": "integer",
                            "description": "Max matches to return. Default 50.",
                        },
                    },
                    "required": ["pattern"],
                },
                handler=self._grep,
            )
        )
        self.register(
            ToolSpec(
                name="search_files",
                description="Find files by path/name substring (case-insensitive).",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Substring to match in file paths.",
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory to search under. Default: '.'",
                        },
                    },
                    "required": ["query"],
                },
                handler=self._search_files,
            )
        )
        self.register(
            ToolSpec(
                name="git_status",
                description=(
                    "Show git working-tree status (branch, staged, unstaged, untracked). "
                    "Use before summarizing changes or deciding what to commit."
                ),
                parameters={"type": "object", "properties": {}, "required": []},
                handler=self._git_status,
            )
        )
        self.register(
            ToolSpec(
                name="git_diff",
                description=(
                    "Show git diff for unstaged (default) or staged changes. "
                    "Optionally limit to a workspace-relative path."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Optional workspace-relative file or directory.",
                        },
                        "staged": {
                            "type": "boolean",
                            "description": "If true, show staged (--cached) diff. Default false.",
                        },
                    },
                    "required": [],
                },
                handler=self._git_diff,
            )
        )
        self.register(
            ToolSpec(
                name="git_log",
                description="Show recent commits (oneline). Useful for style and recent context.",
                parameters={
                    "type": "object",
                    "properties": {
                        "max_count": {
                            "type": "integer",
                            "description": "Number of commits (1-50). Default 10.",
                        }
                    },
                    "required": [],
                },
                handler=self._git_log,
            )
        )
        self.register(
            ToolSpec(
                name="git_commit",
                description=(
                    "Create a git commit. Only when the user clearly asks to commit. "
                    "Requires confirm=true and a message. "
                    "Optional paths= stages those files; "
                    "otherwise stages tracked changes (git add -u). "
                    "Does not push. Does not amend or skip hooks."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Commit message (required).",
                        },
                        "confirm": {
                            "type": "boolean",
                            "description": "Must be true to proceed.",
                        },
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional workspace-relative paths to stage. "
                                "Omit to stage tracked modifications only."
                            ),
                        },
                    },
                    "required": ["message", "confirm"],
                },
                handler=self._git_commit,
            )
        )

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    async def execute(self, name: str, arguments_json: str) -> str:
        spec = self._tools.get(name)
        if spec is None:
            return f"ERROR: unknown tool: {name}"
        args = parse_tool_arguments(arguments_json)
        if "_error" in args:
            return f"ERROR: invalid tool arguments JSON: {arguments_json}"
        try:
            result = spec.handler(**args)
            if hasattr(result, "__await__"):
                result = await result  # type: ignore[misc]
            return str(result)
        except TypeError as exc:
            return f"ERROR: bad arguments for {name}: {exc}"
        except Exception as exc:  # noqa: BLE001 — surface tool failures to the model
            return f"ERROR: {name} failed: {exc}"

    async def execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Return list of {tool_call_id, name, content} for each tool call."""
        results: list[dict[str, str]] = []
        for tc in tool_calls:
            tc_id = tc.get("id") or ""
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            arguments = fn.get("arguments") or "{}"
            content = await self.execute(name, arguments)
            results.append({"tool_call_id": tc_id, "name": name, "content": content})
        return results

    def _list_dir(self, path: str = ".") -> str:
        return list_dir(self.sandbox, path)

    def _read_file(self, path: str) -> str:
        return read_file(self.sandbox, path)

    def _write_file(self, path: str, content: str) -> str:
        target = self.sandbox.resolve(path)
        before: str | None = None
        action = "created"
        if target.exists() and target.is_file():
            action = "modified"
            before = target.read_text(encoding="utf-8", errors="replace")
        result = write_file(self.sandbox, path, content)
        self.file_changes.append(
            FileChange(path=path, action=action, before=before, after=content)
        )
        return result

    def clear_changes(self) -> None:
        self.file_changes.clear()

    def export_changes(self) -> list[dict[str, Any]]:
        return [
            {
                "path": c.path,
                "action": c.action,
                "before": c.before,
                "after": c.after,
            }
            for c in self.file_changes
        ]

    async def _run_terminal(self, command: str) -> str:
        return await run_terminal(self.sandbox, command)

    def _grep(
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        case_insensitive: bool = False,
        max_matches: int = 50,
    ) -> str:
        return grep_workspace(
            self.sandbox,
            pattern,
            path=path,
            glob=glob,
            case_insensitive=case_insensitive,
            max_matches=max_matches,
        )

    def _search_files(self, query: str, path: str = ".") -> str:
        return search_files(self.sandbox, query, path=path)

    async def _git_status(self) -> str:
        return await git_status(self.sandbox)

    async def _git_diff(self, path: str | None = None, staged: bool = False) -> str:
        return await git_diff(self.sandbox, path=path, staged=staged)

    async def _git_log(self, max_count: int = 10) -> str:
        return await git_log(self.sandbox, max_count=max_count)

    async def _git_commit(
        self,
        message: str,
        confirm: bool = False,
        paths: list[str] | None = None,
    ) -> str:
        return await git_commit(
            self.sandbox,
            message=message,
            confirm=confirm,
            paths=paths,
        )

    def describe(self) -> str:
        return json.dumps(
            [{"name": s.name, "description": s.description} for s in self._tools.values()],
            ensure_ascii=False,
            indent=2,
        )
