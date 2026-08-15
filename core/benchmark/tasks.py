"""Built-in offline coding benchmark tasks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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


def _setup_empty(_root: Path) -> None:
    return


def _setup_add_stub(root: Path) -> None:
    (root / "main.py").write_text(
        'def add(a: int, b: int) -> int:\n    raise NotImplementedError\n',
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
    # Agent should have written findings.txt mentioning MARKER_FIND_ME or line.
    findings = root / "findings.txt"
    if findings.is_file():
        text = findings.read_text(encoding="utf-8")
        if "MARKER_FIND_ME" in text or "unused" in text:
            return True, "findings.txt ok"
    # Also accept if agent only grepped (soft pass via app still present)
    app = root / "app.py"
    if app.is_file() and "MARKER_FIND_ME" in app.read_text(encoding="utf-8"):
        # Without findings, fail — task asked to write findings.txt
        return False, "findings.txt missing"
    return False, "workspace incomplete"


def default_tasks() -> list[BenchTask]:
    return [
        BenchTask(
            id="write_hello",
            title="Create hello.txt",
            prompt=(
                "Create a file hello.txt containing exactly: hello codehub\n"
                "Use the write_file tool."
            ),
            setup=_setup_empty,
            verify=_verify_hello,
            mock_script=[
                ChatCompletionResponse(
                    content=None,
                    tool_calls=[
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": (
                                    '{"path":"hello.txt","content":"hello codehub\\n"}'
                                ),
                            },
                        }
                    ],
                    finish_reason="tool_calls",
                ),
                ChatCompletionResponse(
                    content="Created hello.txt",
                    finish_reason="stop",
                ),
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
            mock_script=[
                ChatCompletionResponse(
                    content=None,
                    tool_calls=[
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": (
                                    '{"path":"main.py","content":'
                                    '"def add(a: int, b: int) -> int:\\n'
                                    '    return a + b\\n"}'
                                ),
                            },
                        }
                    ],
                    finish_reason="tool_calls",
                ),
                ChatCompletionResponse(
                    content="Implemented add()",
                    finish_reason="stop",
                ),
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
            mock_script=[
                ChatCompletionResponse(
                    content=None,
                    tool_calls=[
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "grep",
                                "arguments": '{"pattern":"MARKER_FIND_ME"}',
                            },
                        }
                    ],
                    finish_reason="tool_calls",
                ),
                ChatCompletionResponse(
                    content=None,
                    tool_calls=[
                        {
                            "id": "c2",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": (
                                    '{"path":"findings.txt","content":'
                                    '"Found MARKER_FIND_ME in app.py unused()\\n"}'
                                ),
                            },
                        }
                    ],
                    finish_reason="tool_calls",
                ),
                ChatCompletionResponse(
                    content="Wrote findings.txt",
                    finish_reason="stop",
                ),
            ],
        ),
    ]
