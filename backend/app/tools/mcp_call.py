"""mcp_call tool — proxy calls to MCP servers.

Ref: TDD-03 Section 6.3 (mcp_call — dynamically generated per connection).
Each MCP connection yields one ToolDef per discovered tool, named
``mcp_{connection_name}_{tool_name}``. Timeout: 30 seconds.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import httpx

from app.tools.registry import ExecutionContext, ToolDef

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0


def build_mcp_tools(mcp_connections: list[Any]) -> list[ToolDef]:
    """Generate ToolDef instances for all discovered tools across MCP connections.

    Each discovered tool on each connection becomes a separate ToolDef with
    name ``mcp_{connection_name}_{tool_name}``.
    """
    tools: list[ToolDef] = []

    for conn in mcp_connections:
        conn_name = _sanitize_name(conn.name)
        server_url: str = conn.server_url
        auth_config: dict[str, Any] | None = conn.auth_config_encrypted

        for discovered in conn.discovered_tools or []:
            tool_name = discovered.get("name", "")
            if not tool_name:
                continue

            full_name = f"mcp_{conn_name}_{_sanitize_name(tool_name)}"
            description = discovered.get(
                "description", f"MCP tool: {tool_name}"
            )
            input_schema = discovered.get("input_schema", {
                "type": "object",
                "properties": {},
            })

            executor = _make_executor(
                server_url=server_url,
                mcp_tool_name=tool_name,
                auth_config=auth_config,
            )

            tools.append(ToolDef(
                name=full_name,
                description=description,
                input_schema=input_schema,
                executor=executor,
            ))

    return tools


def _sanitize_name(name: str) -> str:
    """Sanitize a name for use in tool identifiers (lowercase, underscores only)."""
    return re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_").lower()


def _make_executor(
    server_url: str,
    mcp_tool_name: str,
    auth_config: dict[str, Any] | None,
) -> Any:
    """Create an async executor closure bound to a specific MCP connection and tool."""

    async def execute(tool_input: dict[str, Any], context: ExecutionContext) -> str:
        """Proxy a tool call to the MCP server via JSON-RPC."""
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if auth_config:
            api_key = auth_config.get("api_key")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": mcp_tool_name,
                "arguments": tool_input,
            },
            "id": str(uuid.uuid4()),
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    server_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            return (
                f"Error: MCP call to '{mcp_tool_name}' timed out "
                f"after {_TIMEOUT:.0f}s."
            )
        except httpx.HTTPStatusError as exc:
            return (
                f"Error: MCP server returned HTTP {exc.response.status_code} "
                f"for tool '{mcp_tool_name}'."
            )
        except httpx.HTTPError as exc:
            return f"Error: MCP call to '{mcp_tool_name}' failed: {exc}"

        # Handle JSON-RPC error response
        if "error" in data:
            error = data["error"]
            return (
                f"Error: MCP tool '{mcp_tool_name}' returned error: "
                f"{error.get('message', str(error))}"
            )

        # Extract result — MCP result.content is a list of content blocks
        result = data.get("result", {})
        content_blocks = result.get("content", [])
        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        return "\n".join(text_parts) if text_parts else str(result)

    return execute
