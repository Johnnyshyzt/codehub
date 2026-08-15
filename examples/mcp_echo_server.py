"""Minimal MCP echo server for local experiments.

Requires: pip install 'codehub[mcp]'

Run via mcp.json:
  command: python
  args: ["-m", "examples.mcp_echo_server"]
"""

from __future__ import annotations


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Install MCP SDK first: pip install 'codehub[mcp]' or pip install mcp"
        ) from exc

    mcp = FastMCP("codehub-echo")

    @mcp.tool()
    def echo(message: str) -> str:
        """Echo a message back (demo MCP tool)."""
        return f"echo: {message}"

    mcp.run()


if __name__ == "__main__":
    main()
