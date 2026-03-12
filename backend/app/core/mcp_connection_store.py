import json
import logging
import threading
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.core.mcp_client import discover_mcp_tools, test_mcp_connection
from app.models.mcp import (
    McpConnectionConfig,
    McpConnectionCreateRequest,
    McpConnectionResponse,
    McpConnectionStatus,
    McpConnectionUpdateRequest,
    McpTestResult,
    McpToolDescriptor,
    McpUsageSummary,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _to_response(connection: McpConnectionConfig) -> McpConnectionResponse:
    return McpConnectionResponse(
        id=connection.id,
        name=connection.name,
        transport=connection.transport,
        endpoint_url=connection.endpoint_url,
        enabled=connection.enabled,
        auth_header_name=connection.auth_header_name,
        has_auth_token=bool(connection.auth_token.strip()),
        notes=connection.notes,
        tool_allowlist=list(connection.tool_allowlist),
        discovered_tools=list(connection.discovered_tools),
        status=connection.status,
        last_tested_at=connection.last_tested_at,
        last_error=connection.last_error,
        total_calls=connection.total_calls,
        total_failures=connection.total_failures,
        last_called_at=connection.last_called_at,
    )


class McpConnectionStore:
    def __init__(self):
        settings = get_settings()
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self._file = data_dir / "mcp_connections.json"
        self._lock = threading.Lock()
        self._connections: dict[str, McpConnectionConfig] = {}
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read MCP connections store: %s", exc)
            return
        if not isinstance(payload, dict):
            return
        connections: dict[str, McpConnectionConfig] = {}
        for connection_id, item in payload.items():
            try:
                connections[connection_id] = McpConnectionConfig.model_validate(item)
            except Exception as exc:
                logger.warning("Skipping invalid MCP connection %s: %s", connection_id, exc)
        self._connections = connections

    def _save(self) -> None:
        payload = {connection_id: connection.model_dump(mode="json") for connection_id, connection in self._connections.items()}
        self._file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list_connections(self) -> list[McpConnectionResponse]:
        with self._lock:
            return [_to_response(connection) for connection in sorted(self._connections.values(), key=lambda item: item.name.lower())]

    def get_connection(self, connection_id: str) -> Optional[McpConnectionConfig]:
        with self._lock:
            connection = self._connections.get(connection_id)
            return connection.model_copy(deep=True) if connection else None

    def create_connection(self, request: McpConnectionCreateRequest) -> McpConnectionResponse:
        with self._lock:
            connection = McpConnectionConfig(
                id=str(uuid.uuid4()),
                name=request.name.strip(),
                endpoint_url=request.endpoint_url,
                enabled=request.enabled,
                auth_header_name=request.auth_header_name.strip() or "Authorization",
                auth_token=request.auth_token.strip(),
                notes=request.notes.strip(),
                tool_allowlist=list(request.tool_allowlist),
            )
            self._connections[connection.id] = connection
            self._save()
            return _to_response(connection)

    def update_connection(self, connection_id: str, request: McpConnectionUpdateRequest) -> McpConnectionResponse:
        with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                raise ValueError("MCP connection not found")
            updates = request.model_dump(exclude_unset=True)
            if "name" in updates and request.name is not None:
                connection.name = request.name.strip()
            if "endpoint_url" in updates and request.endpoint_url is not None:
                connection.endpoint_url = request.endpoint_url
            if "enabled" in updates and request.enabled is not None:
                connection.enabled = request.enabled
            if "auth_header_name" in updates and request.auth_header_name is not None:
                connection.auth_header_name = request.auth_header_name.strip() or "Authorization"
            if request.clear_auth_token:
                connection.auth_token = ""
            elif "auth_token" in updates and request.auth_token is not None:
                connection.auth_token = request.auth_token.strip()
            if "notes" in updates and request.notes is not None:
                connection.notes = request.notes.strip()
            if "tool_allowlist" in updates and request.tool_allowlist is not None:
                connection.tool_allowlist = list(request.tool_allowlist)
            self._save()
            return _to_response(connection)

    def delete_connection(self, connection_id: str) -> None:
        with self._lock:
            if connection_id not in self._connections:
                raise ValueError("MCP connection not found")
            del self._connections[connection_id]
            self._save()

    def list_tools(self, connection_id: str) -> list[McpToolDescriptor]:
        with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                raise ValueError("MCP connection not found")
            tools = list(connection.discovered_tools)
            if connection.tool_allowlist:
                allowed = set(connection.tool_allowlist)
                tools = [tool for tool in tools if tool.name in allowed]
            return tools

    def test_connection(self, connection_id: str) -> McpTestResult:
        connection = self.get_connection(connection_id)
        if connection is None:
            raise ValueError("MCP connection not found")
        result = test_mcp_connection(connection)
        with self._lock:
            target = self._connections.get(connection_id)
            if target is None:
                raise ValueError("MCP connection not found")
            target.status = result.status
            target.last_tested_at = _now_iso()
            target.last_error = result.error
            self._save()
        return result

    def discover_tools(self, connection_id: str) -> list[McpToolDescriptor]:
        connection = self.get_connection(connection_id)
        if connection is None:
            raise ValueError("MCP connection not found")
        tools = discover_mcp_tools(connection)
        with self._lock:
            target = self._connections.get(connection_id)
            if target is None:
                raise ValueError("MCP connection not found")
            target.discovered_tools = tools
            target.status = McpConnectionStatus.HEALTHY
            target.last_tested_at = _now_iso()
            target.last_error = None
            self._save()
        return list(tools)

    def record_tool_call(self, connection_id: str, *, success: bool, error: str | None = None) -> None:
        with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                return
            connection.total_calls += 1
            connection.last_called_at = _now_iso()
            if success:
                connection.status = McpConnectionStatus.HEALTHY
                connection.last_error = None
            else:
                connection.total_failures += 1
                connection.status = McpConnectionStatus.DEGRADED
                connection.last_error = error
            self._save()

    def summarize_usage(self) -> McpUsageSummary:
        connections = self.list_connections()
        summary = McpUsageSummary(connections=connections)
        summary.total_connections = len(connections)
        summary.healthy_connections = sum(1 for connection in connections if connection.status == McpConnectionStatus.HEALTHY)
        summary.degraded_connections = sum(1 for connection in connections if connection.status == McpConnectionStatus.DEGRADED)
        summary.unavailable_connections = sum(1 for connection in connections if connection.status == McpConnectionStatus.UNAVAILABLE)
        summary.total_calls = sum(connection.total_calls for connection in connections)
        summary.total_failures = sum(connection.total_failures for connection in connections)
        return summary


@lru_cache(maxsize=1)
def get_mcp_connection_store() -> McpConnectionStore:
    return McpConnectionStore()
