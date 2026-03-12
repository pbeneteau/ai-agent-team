import json
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any
import uuid

import httpx

from app.config.tool_runtime import (
    MCP_CONNECTION_TEST_TIMEOUT_SECONDS,
    MCP_TOOL_CALL_TIMEOUT_SECONDS,
)
from app.models.mcp import (
    McpCapabilityClass,
    McpConnectionConfig,
    McpTestResult,
    McpToolDescriptor,
)

logger = logging.getLogger(__name__)

_CLIENT_PROTOCOL_VERSION = "2024-11-05"


class McpClientError(RuntimeError):
    pass


@dataclass
class McpToolCallResult:
    content: str
    duration_ms: int


def _now_duration_ms(start: float) -> int:
    return int((monotonic() - start) * 1000)


def _json_rpc_request(method: str, *, params: dict[str, Any] | None = None, with_id: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    if with_id:
        payload["id"] = str(uuid.uuid4())
    return payload


def _build_auth_headers(connection: McpConnectionConfig) -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    token = connection.auth_token.strip()
    if token:
        header_name = connection.auth_header_name.strip() or "Authorization"
        headers[header_name] = token
    return headers


def _extract_session_id(response: httpx.Response) -> str | None:
    for key in ("mcp-session-id", "Mcp-Session-Id", "MCP-Session-Id"):
        value = response.headers.get(key)
        if value:
            return value
    return None


def _extract_json_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception as exc:
        raise McpClientError(f"Invalid MCP JSON response: {exc}") from exc
    if not isinstance(payload, dict):
        raise McpClientError("Invalid MCP response payload: expected an object")
    if "error" in payload:
        error = payload.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise McpClientError(str(message or "Unknown MCP error"))
    return payload


def _normalize_input_schema(schema: Any) -> dict[str, Any]:
    if isinstance(schema, dict):
        return schema
    return {}


def _infer_capability(tool_name: str) -> tuple[bool, McpCapabilityClass]:
    normalized = tool_name.lower().strip()
    read_prefixes = (
        "get",
        "list",
        "read",
        "search",
        "find",
        "fetch",
        "lookup",
        "query",
        "describe",
    )
    write_prefixes = (
        "create",
        "update",
        "delete",
        "write",
        "insert",
        "remove",
        "send",
        "post",
        "put",
        "patch",
        "execute",
        "run",
    )
    if normalized.startswith(read_prefixes):
        return True, McpCapabilityClass.READ_ONLY
    if normalized.startswith(write_prefixes):
        return False, McpCapabilityClass.WRITE
    return True, McpCapabilityClass.UNKNOWN


def _normalize_tool_descriptor(raw: Any) -> McpToolDescriptor | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip()
    if not name:
        return None
    description = str(raw.get("description", "") or "").strip()
    input_schema = _normalize_input_schema(raw.get("inputSchema") or raw.get("input_schema"))
    read_only, capability_class = _infer_capability(name)
    return McpToolDescriptor(
        name=name,
        description=description,
        input_schema=input_schema,
        read_only=read_only,
        capability_class=capability_class,
    )


def _render_tool_content(result: Any) -> str:
    if not isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, indent=2)
    content = result.get("content")
    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                item_type = str(item.get("type", "")).strip().lower()
                if item_type == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, indent=2))
            else:
                parts.append(str(item))
    structured = result.get("structuredContent")
    if structured is not None:
        parts.append(json.dumps(structured, ensure_ascii=False, indent=2))
    if not parts:
        parts.append(json.dumps(result, ensure_ascii=False, indent=2))
    return "\n\n".join(part for part in parts if part.strip()).strip()


class McpHttpClient:
    def __init__(self, connection: McpConnectionConfig, *, timeout_seconds: int):
        self.connection = connection
        self.timeout_seconds = timeout_seconds
        self.session_id: str | None = None

    def _post(self, request_payload: dict[str, Any], *, with_id: bool = True) -> dict[str, Any]:
        headers = _build_auth_headers(self.connection)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(str(self.connection.endpoint_url), json=request_payload, headers=headers)
        response.raise_for_status()
        session_id = _extract_session_id(response)
        if session_id:
            self.session_id = session_id
        if not with_id and not response.content.strip():
            return {}
        payload = _extract_json_payload(response)
        if with_id and "result" not in payload:
            raise McpClientError("Invalid MCP response: missing result")
        return payload

    def initialize(self) -> McpTestResult:
        payload = _json_rpc_request(
            "initialize",
            params={
                "protocolVersion": _CLIENT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "ai-agent-team", "version": "0.1.0"},
            },
        )
        try:
            result_payload = self._post(payload)
            result = result_payload.get("result") or {}
            if not isinstance(result, dict):
                raise McpClientError("Invalid MCP initialize result")
            self._post(_json_rpc_request("notifications/initialized", with_id=False), with_id=False)
            server_info = result.get("serverInfo") or {}
            server_name = str(server_info.get("name", "")).strip() or None
            server_version = str(server_info.get("version", "")).strip() or None
            protocol_version = str(result.get("protocolVersion", "")).strip() or None
            return McpTestResult(
                ok=True,
                status="healthy",
                server_name=server_name,
                server_version=server_version,
                protocol_version=protocol_version,
            )
        except Exception as exc:
            message = str(exc)
            logger.warning("MCP initialize failed for %s: %s", self.connection.name, message)
            return McpTestResult(ok=False, status="unavailable", error=message)

    def list_tools(self) -> list[McpToolDescriptor]:
        init_result = self.initialize()
        if not init_result.ok:
            raise McpClientError(init_result.error or "Unable to initialize MCP connection")
        payload = self._post(_json_rpc_request("tools/list"))
        result = payload.get("result") or {}
        raw_tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(raw_tools, list):
            return []
        descriptors: list[McpToolDescriptor] = []
        for raw_tool in raw_tools:
            descriptor = _normalize_tool_descriptor(raw_tool)
            if descriptor is not None:
                descriptors.append(descriptor)
        return descriptors

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> McpToolCallResult:
        start = monotonic()
        init_result = self.initialize()
        if not init_result.ok:
            raise McpClientError(init_result.error or "Unable to initialize MCP connection")
        payload = self._post(
            _json_rpc_request(
                "tools/call",
                params={
                    "name": tool_name,
                    "arguments": arguments or {},
                },
            )
        )
        result = payload.get("result") or {}
        return McpToolCallResult(
            content=_render_tool_content(result),
            duration_ms=_now_duration_ms(start),
        )


def test_mcp_connection(connection: McpConnectionConfig) -> McpTestResult:
    client = McpHttpClient(connection, timeout_seconds=MCP_CONNECTION_TEST_TIMEOUT_SECONDS)
    return client.initialize()


def discover_mcp_tools(connection: McpConnectionConfig) -> list[McpToolDescriptor]:
    client = McpHttpClient(connection, timeout_seconds=MCP_CONNECTION_TEST_TIMEOUT_SECONDS)
    return client.list_tools()


def call_mcp_tool(
    connection: McpConnectionConfig,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> McpToolCallResult:
    client = McpHttpClient(connection, timeout_seconds=MCP_TOOL_CALL_TIMEOUT_SECONDS)
    return client.call_tool(tool_name, arguments)
