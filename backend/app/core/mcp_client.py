"""MCP protocol client for tool discovery and proxied calls.

Ref: TDD-04 Section 11 (MCP connections).

Communicates with MCP servers over HTTP using the MCP JSON-RPC protocol.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MCP_TIMEOUT = 30.0  # seconds per MCP call


class McpClientError(Exception):
    """Error communicating with an MCP server."""


async def discover_tools(
    server_url: str,
    auth_config: dict[str, Any] | None = None,
    auth_type: str = "none",
) -> list[dict[str, Any]]:
    """Discover available tools on an MCP server via tools/list.

    Returns a list of tool definitions, each containing:
    - name: str
    - description: str
    - input_schema: dict
    """
    headers = _build_headers(auth_config, auth_type)

    async with httpx.AsyncClient(timeout=MCP_TIMEOUT) as client:
        try:
            resp = await client.post(
                server_url.rstrip("/"),
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
                headers=headers,
            )

            if resp.status_code != 200:
                raise McpClientError(
                    f"MCP server returned {resp.status_code}: {resp.text}"
                )

            data = resp.json()

            if "error" in data:
                raise McpClientError(
                    f"MCP server error: {data['error']}"
                )

            result = data.get("result", {})
            tools = result.get("tools", [])

            return [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "input_schema": t.get("inputSchema", t.get("input_schema", {})),
                }
                for t in tools
            ]

        except httpx.RequestError as exc:
            raise McpClientError(f"Failed to connect to MCP server: {exc}") from exc


async def ping_server(
    server_url: str,
    auth_config: dict[str, Any] | None = None,
    auth_type: str = "none",
) -> dict[str, Any]:
    """Ping an MCP server and return status info.

    Returns:
        {ok: bool, server_version: str, tools_count: int, latency_ms: int}
    """
    headers = _build_headers(auth_config, auth_type)

    start = time.monotonic()

    async with httpx.AsyncClient(timeout=MCP_TIMEOUT) as client:
        try:
            # Try tools/list as a health check
            resp = await client.post(
                server_url.rstrip("/"),
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
                headers=headers,
            )

            latency_ms = int((time.monotonic() - start) * 1000)

            if resp.status_code != 200:
                return {
                    "ok": False,
                    "server_version": "",
                    "tools_count": 0,
                    "latency_ms": latency_ms,
                }

            data = resp.json()
            result = data.get("result", {})
            tools = result.get("tools", [])

            return {
                "ok": True,
                "server_version": result.get("server_version", "unknown"),
                "tools_count": len(tools),
                "latency_ms": latency_ms,
            }

        except (httpx.RequestError, Exception) as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("MCP ping failed: %s", exc)
            return {
                "ok": False,
                "server_version": "",
                "tools_count": 0,
                "latency_ms": latency_ms,
            }


async def call_tool(
    server_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    auth_config: dict[str, Any] | None = None,
    auth_type: str = "none",
) -> Any:
    """Call a tool on an MCP server.

    Returns the tool's result payload.
    Timeout: 30 seconds per call (TDD-04 Section 11.1).
    """
    headers = _build_headers(auth_config, auth_type)

    async with httpx.AsyncClient(timeout=MCP_TIMEOUT) as client:
        try:
            resp = await client.post(
                server_url.rstrip("/"),
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                },
                headers=headers,
            )

            if resp.status_code != 200:
                raise McpClientError(
                    f"MCP tool call failed: {resp.status_code} {resp.text}"
                )

            data = resp.json()
            if "error" in data:
                raise McpClientError(f"MCP tool error: {data['error']}")

            return data.get("result")

        except httpx.RequestError as exc:
            raise McpClientError(f"MCP tool call failed: {exc}") from exc


def _build_headers(
    auth_config: dict[str, Any] | None,
    auth_type: str,
) -> dict[str, str]:
    """Build HTTP headers for MCP requests based on auth type."""
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if auth_type == "api_key" and auth_config:
        api_key = auth_config.get("api_key", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

    elif auth_type == "oauth" and auth_config:
        access_token = auth_config.get("access_token", "")
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

    return headers
