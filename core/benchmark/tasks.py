"""Built-in offline coding benchmark tasks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from providers.base import ChatCompletionResponse

VerifyFn = Callable[[Path], tuple[bool, str]]
SetupFn = Callable[[Path], None]


@dataclass
class BenchTask:
    id: str
    title: str
    prompt: str
    setup: SetupFn
    verify: VerifyFn
    mock_script: list[ChatCompletionResponse]
    tags: tuple[str, ...] = ()


def _tool(
    call_id: str,
    name: str,
    arguments: dict[str, Any] | str,
) -> ChatCompletionResponse:
    if isinstance(arguments, dict):
        args = json.dumps(arguments, ensure_ascii=False)
    else:
        args = arguments
    return ChatCompletionResponse(
        content=None,
        tool_calls=[
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        ],
        finish_reason="tool_calls",
    )


def _final(content: str) -> ChatCompletionResponse:
    return ChatCompletionResponse(content=content, finish_reason="stop")


def _setup_empty(_root: Path) -> None:
    return


def _setup_add_stub(root: Path) -> None:
    (root / "main.py").write_text(
        "def add(a: int, b: int) -> int:\n    raise NotImplementedError\n",
        encoding="utf-8",
    )
    (root / "test_main.py").write_text(
        "from main import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )


def _setup_search(root: Path) -> None:
    (root / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n\n"
        "def unused():\n    # MARKER_FIND_ME\n    return 1\n",
        encoding="utf-8",
    )


def _setup_buggy_mul(root: Path) -> None:
    (root / "calc.py").write_text(
        "def mul(a: int, b: int) -> int:\n    return a - b  # bug: should multiply\n",
        encoding="utf-8",
    )


def _setup_inventory(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("B = 2\n", encoding="utf-8")
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")


def _setup_hidden_key(root: Path) -> None:
    (root / "configs").mkdir()
    (root / "configs" / "app.toml").write_text("name = 'demo'\n", encoding="utf-8")
    (root / "configs" / "secret.key").write_text("KEY=demo-secret\n", encoding="utf-8")
    (root / "readme.txt").write_text("look in configs/\n", encoding="utf-8")


def _setup_factorial(root: Path) -> None:
    (root / "mathlib.py").write_text(
        "def factorial(n: int) -> int:\n    raise NotImplementedError\n",
        encoding="utf-8",
    )
    (root / "test_mathlib.py").write_text(
        "from mathlib import factorial\n\n\n"
        "def test_factorial():\n"
        "    assert factorial(0) == 1\n"
        "    assert factorial(5) == 120\n",
        encoding="utf-8",
    )


def _verify_hello(root: Path) -> tuple[bool, str]:
    path = root / "hello.txt"
    if not path.is_file():
        return False, "hello.txt missing"
    text = path.read_text(encoding="utf-8").strip()
    if "hello codehub" not in text.lower():
        return False, f"unexpected content: {text!r}"
    return True, "hello.txt ok"


def _verify_add(root: Path) -> tuple[bool, str]:
    main = root / "main.py"
    if not main.is_file():
        return False, "main.py missing"
    text = main.read_text(encoding="utf-8")
    ns: dict = {}
    try:
        exec(compile(text, str(main), "exec"), ns, ns)
        add = ns.get("add")
        if not callable(add):
            return False, "add() not defined"
        if add(2, 3) != 5 or add(-1, 1) != 0:
            return False, "add() incorrect"
    except Exception as exc:  # noqa: BLE001
        return False, f"exec failed: {exc}"
    return True, "add() ok"


def _verify_marker(root: Path) -> tuple[bool, str]:
    findings = root / "findings.txt"
    if findings.is_file():
        text = findings.read_text(encoding="utf-8")
        if "MARKER_FIND_ME" in text or "unused" in text:
            return True, "findings.txt ok"
    app = root / "app.py"
    if app.is_file() and "MARKER_FIND_ME" in app.read_text(encoding="utf-8"):
        return False, "findings.txt missing"
    return False, "workspace incomplete"


def _verify_mul(root: Path) -> tuple[bool, str]:
    path = root / "calc.py"
    if not path.is_file():
        return False, "calc.py missing"
    ns: dict = {}
    try:
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns, ns)
        mul = ns.get("mul")
        if not callable(mul):
            return False, "mul() not defined"
        if mul(3, 4) != 12 or mul(0, 5) != 0:
            return False, "mul() still incorrect"
    except Exception as exc:  # noqa: BLE001
        return False, f"exec failed: {exc}"
    return True, "mul() ok"


def _verify_config(root: Path) -> tuple[bool, str]:
    path = root / "config.json"
    if not path.is_file():
        return False, "config.json missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, f"invalid json: {exc}"
    if data.get("name") != "codehub" or data.get("version") != "0.3.0":
        return False, f"unexpected config: {data!r}"
    if not isinstance(data.get("features"), list) or "bench" not in data["features"]:
        return False, "features must include 'bench'"
    return True, "config.json ok"


def _verify_inventory(root: Path) -> tuple[bool, str]:
    path = root / "inventory.txt"
    if not path.is_file():
        return False, "inventory.txt missing"
    text = path.read_text(encoding="utf-8").lower()
    if "readme" not in text and "src" not in text:
        return False, "inventory missing expected entries"
    return True, "inventory.txt ok"


def _verify_secret_key(root: Path) -> tuple[bool, str]:
    path = root / "found_key.txt"
    if not path.is_file():
        return False, "found_key.txt missing"
    text = path.read_text(encoding="utf-8")
    if "secret.key" not in text and "demo-secret" not in text:
        return False, "found_key.txt does not mention secret.key"
    return True, "found_key.txt ok"


def _verify_factorial(root: Path) -> tuple[bool, str]:
    path = root / "mathlib.py"
    if not path.is_file():
        return False, "mathlib.py missing"
    ns: dict = {}
    try:
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns, ns)
        factorial = ns.get("factorial")
        if not callable(factorial):
            return False, "factorial() not defined"
        if factorial(0) != 1 or factorial(5) != 120:
            return False, "factorial() incorrect"
    except Exception as exc:  # noqa: BLE001
        return False, f"exec failed: {exc}"
    return True, "factorial() ok"


def default_tasks(*, only: Optional[list[str]] = None) -> list[BenchTask]:
    """Return built-in tasks, optionally filtered by id."""
    tasks = [
        BenchTask(
            id="write_hello",
            title="Create hello.txt",
            prompt=(
                "Create a file hello.txt containing exactly: hello codehub\n"
                "Use the write_file tool."
            ),
            setup=_setup_empty,
            verify=_verify_hello,
            tags=("write", "smoke"),
            mock_script=[
                _tool("c1", "write_file", {"path": "hello.txt", "content": "hello codehub\n"}),
                _final("Created hello.txt"),
            ],
        ),
        BenchTask(
            id="implement_add",
            title="Implement add()",
            prompt=(
                "Implement add(a, b) in main.py to return a + b. "
                "Use write_file or read_file tools as needed."
            ),
            setup=_setup_add_stub,
            verify=_verify_add,
            tags=("edit", "python"),
            mock_script=[
                _tool(
                    "c1",
                    "write_file",
                    {
                        "path": "main.py",
                        "content": "def add(a: int, b: int) -> int:\n    return a + b\n",
                    },
                ),
                _final("Implemented add()"),
            ],
        ),
        BenchTask(
            id="find_marker",
            title="Find MARKER_FIND_ME",
            prompt=(
                "Search the workspace for MARKER_FIND_ME using grep, then write "
                "findings.txt summarizing where it was found."
            ),
            setup=_setup_search,
            verify=_verify_marker,
            tags=("grep", "search"),
            mock_script=[
                _tool("c1", "grep", {"pattern": "MARKER_FIND_ME"}),
                _tool(
                    "c2",
                    "write_file",
                    {
                        "path": "findings.txt",
                        "content": "Found MARKER_FIND_ME in app.py unused()\n",
                    },
                ),
                _final("Wrote findings.txt"),
            ],
        ),
        BenchTask(
            id="fix_mul_bug",
            title="Fix mul() bug",
            prompt=(
                "calc.py has a buggy mul(a, b) that subtracts instead of multiplying. "
                "Read the file, fix it to return a * b, and save with write_file."
            ),
            setup=_setup_buggy_mul,
            verify=_verify_mul,
            tags=("edit", "debug", "python"),
            mock_script=[
                _tool("c1", "read_file", {"path": "calc.py"}),
                _tool(
                    "c2",
                    "write_file",
                    {
                        "path": "calc.py",
                        "content": "def mul(a: int, b: int) -> int:\n    return a * b\n",
                    },
                ),
                _final("Fixed mul()"),
            ],
        ),
        BenchTask(
            id="write_config",
            title="Write config.json",
            prompt=(
                "Create config.json with JSON object: "
                '{"name":"codehub","version":"0.3.0","features":["bench","mcp"]}. '
                "Use write_file."
            ),
            setup=_setup_empty,
            verify=_verify_config,
            tags=("write", "json"),
            mock_script=[
                _tool(
                    "c1",
                    "write_file",
                    {
                        "path": "config.json",
                        "content": json.dumps(
                            {
                                "name": "codehub",
                                "version": "0.3.0",
                                "features": ["bench", "mcp"],
                            }
                        )
                        + "\n",
                    },
                ),
                _final("Wrote config.json"),
            ],
        ),
        BenchTask(
            id="list_inventory",
            title="List workspace inventory",
            prompt=(
                "Use list_dir on . and/or src, then write inventory.txt listing "
                "the important paths you found (include README and src)."
            ),
            setup=_setup_inventory,
            verify=_verify_inventory,
            tags=("list_dir", "write"),
            mock_script=[
                _tool("c1", "list_dir", {"path": "."}),
                _tool(
                    "c2",
                    "write_file",
                    {
                        "path": "inventory.txt",
                        "content": "README.md\nsrc/\nsrc/a.py\nsrc/b.py\n",
                    },
                ),
                _final("Wrote inventory.txt"),
            ],
        ),
        BenchTask(
            id="find_secret_key",
            title="Find secret.key via search_files",
            prompt=(
                "Use search_files to locate secret.key, then write found_key.txt "
                "mentioning the path (and optionally the KEY value)."
            ),
            setup=_setup_hidden_key,
            verify=_verify_secret_key,
            tags=("search_files", "write"),
            mock_script=[
                _tool("c1", "search_files", {"query": "secret.key"}),
                _tool(
                    "c2",
                    "write_file",
                    {
                        "path": "found_key.txt",
                        "content": "Found configs/secret.key (KEY=demo-secret)\n",
                    },
                ),
                _final("Wrote found_key.txt"),
            ],
        ),
        BenchTask(
            id="implement_factorial",
            title="Implement factorial()",
            prompt=(
                "Implement factorial(n) in mathlib.py (0! = 1). "
                "You may run_terminal with pytest if helpful."
            ),
            setup=_setup_factorial,
            verify=_verify_factorial,
            tags=("edit", "python", "tests"),
            mock_script=[
                _tool(
                    "c1",
                    "write_file",
                    {
                        "path": "mathlib.py",
                        "content": (
                            "def factorial(n: int) -> int:\n"
                            "    if n < 0:\n"
                            "        raise ValueError(n)\n"
                            "    out = 1\n"
                            "    for i in range(2, n + 1):\n"
                            "        out *= i\n"
                            "    return out\n"
                        ),
                    },
                ),
                _tool("c2", "run_terminal", {"command": "python -m pytest -q"}),
                _final("Implemented factorial and ran tests"),
            ],
        ),
    ]
    if only:
        wanted = {x.strip() for x in only if x.strip()}
        selected = [t for t in tasks if t.id in wanted]
        missing = wanted - {t.id for t in selected}
        if missing:
            known = ", ".join(t.id for t in tasks)
            raise ValueError(
                f"Unknown bench task id(s): {sorted(missing)}. Known: {known}"
            )
        return selected
    return tasks


def list_task_ids() -> list[str]:
    return [t.id for t in default_tasks()]
