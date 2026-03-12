from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


class McpTransport(str, Enum):
    STREAMABLE_HTTP = "streamable_http"


class McpConnectionStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class McpApprovalMode(str, Enum):
    AUTO = "auto"
    CONFIRM_EACH_USE = "confirm_each_use"
    BLOCKED = "blocked"


class McpCapabilityClass(str, Enum):
    READ_ONLY = "read_only"
    WRITE = "write"
    UNKNOWN = "unknown"


class McpToolDescriptor(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True
    capability_class: McpCapabilityClass = McpCapabilityClass.READ_ONLY


class McpConnectionConfig(BaseModel):
    id: str
    name: str
    transport: McpTransport = McpTransport.STREAMABLE_HTTP
    endpoint_url: HttpUrl
    enabled: bool = True
    auth_header_name: str = "Authorization"
    auth_token: str = ""
    notes: str = ""
    tool_allowlist: list[str] = Field(default_factory=list)
    discovered_tools: list[McpToolDescriptor] = Field(default_factory=list)
    status: McpConnectionStatus = McpConnectionStatus.UNKNOWN
    last_tested_at: Optional[str] = None
    last_error: Optional[str] = None
    total_calls: int = 0
    total_failures: int = 0
    last_called_at: Optional[str] = None


class McpConnectionResponse(BaseModel):
    id: str
    name: str
    transport: McpTransport
    endpoint_url: HttpUrl
    enabled: bool
    auth_header_name: str
    has_auth_token: bool
    notes: str
    tool_allowlist: list[str]
    discovered_tools: list[McpToolDescriptor]
    status: McpConnectionStatus
    last_tested_at: Optional[str] = None
    last_error: Optional[str] = None
    total_calls: int = 0
    total_failures: int = 0
    last_called_at: Optional[str] = None


class McpConnectionCreateRequest(BaseModel):
    name: str
    endpoint_url: HttpUrl
    enabled: bool = True
    auth_header_name: str = "Authorization"
    auth_token: str = ""
    notes: str = ""
    tool_allowlist: list[str] = Field(default_factory=list)


class McpConnectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    endpoint_url: Optional[HttpUrl] = None
    enabled: Optional[bool] = None
    auth_header_name: Optional[str] = None
    auth_token: Optional[str] = None
    clear_auth_token: bool = False
    notes: Optional[str] = None
    tool_allowlist: Optional[list[str]] = None


class McpTestResult(BaseModel):
    ok: bool
    status: McpConnectionStatus
    server_name: Optional[str] = None
    server_version: Optional[str] = None
    protocol_version: Optional[str] = None
    error: Optional[str] = None


class AgentMcpToolBinding(BaseModel):
    connection_id: str
    tool_name: str
    enabled: bool = True
    alias: Optional[str] = None
    approval_mode: McpApprovalMode = McpApprovalMode.AUTO


class AgentMcpToolBindingResolved(BaseModel):
    connection_id: str
    connection_name: str
    tool_name: str
    enabled: bool
    alias: Optional[str] = None
    approval_mode: McpApprovalMode
    description: str = ""
    read_only: bool = True
    capability_class: McpCapabilityClass = McpCapabilityClass.READ_ONLY
    connection_status: McpConnectionStatus = McpConnectionStatus.UNKNOWN


class AgentMcpBindingUpdateRequest(BaseModel):
    bindings: list[AgentMcpToolBinding] = Field(default_factory=list)


class McpUsageSummary(BaseModel):
    total_connections: int = 0
    healthy_connections: int = 0
    degraded_connections: int = 0
    unavailable_connections: int = 0
    total_calls: int = 0
    total_failures: int = 0
    connections: list[McpConnectionResponse] = Field(default_factory=list)
