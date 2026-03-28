"""Pydantic schemas for MCP connection endpoints.

Ref: TDD-04 Section 11.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class McpToolItem(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class McpConnectionItem(BaseModel):
    id: str
    name: str
    server_url: str
    auth_type: str
    status: str
    discovered_tools: list[McpToolItem] = Field(default_factory=list)
    last_verified_at: datetime | None = None
    created_at: datetime


class CreateMcpConnectionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    server_url: str = Field(..., min_length=1)
    auth_type: str = Field(default="none", pattern="^(api_key|oauth|none)$")
    auth_config: dict[str, Any] | None = None


class TestMcpResponse(BaseModel):
    ok: bool
    server_version: str = ""
    tools_count: int = 0
    latency_ms: int = 0


class DiscoverToolsResponse(BaseModel):
    tools: list[McpToolItem]
