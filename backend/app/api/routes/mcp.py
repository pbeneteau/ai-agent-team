"""MCP connection CRUD endpoints.

Ref: TDD-04 Section 11.
Auth config stored encrypted, never returned in plaintext.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.mcp import (
    CreateMcpConnectionRequest,
    DiscoverToolsResponse,
    McpConnectionItem,
    McpToolItem,
    TestMcpResponse,
)
from app.core.database import get_db
from app.core.encryption import decrypt_json, encrypt_json
from app.core.errors import not_found
from app.core.mcp_client import McpClientError, discover_tools, ping_server
from app.core.workspace_id import get_workspace_id
from app.models.mcp_connection import McpConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# GET /api/mcp/connections — list
# ---------------------------------------------------------------------------


@router.get("/connections")
async def list_connections(
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(McpConnection)
        .where(McpConnection.workspace_id == workspace_id)
        .order_by(McpConnection.created_at.desc())
    )
    connections = result.scalars().all()

    items = [_to_response(c).model_dump(mode="json") for c in connections]
    return {"items": items}


# ---------------------------------------------------------------------------
# POST /api/mcp/connections — create
# ---------------------------------------------------------------------------


@router.post("/connections", status_code=201)
async def create_connection(
    body: CreateMcpConnectionRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Encrypt auth config if provided
    encrypted_config: str | None = None
    if body.auth_config:
        encrypted_config = encrypt_json(body.auth_config)

    conn = McpConnection(
        workspace_id=workspace_id,
        name=body.name,
        server_url=body.server_url,
        auth_type=body.auth_type,
        auth_config_encrypted=encrypted_config,
    )

    # Attempt tool discovery
    try:
        tools = await discover_tools(
            server_url=body.server_url,
            auth_config=body.auth_config,
            auth_type=body.auth_type,
        )
        conn.discovered_tools = tools
        conn.status = "active"
        conn.last_verified_at = datetime.now(timezone.utc)
    except McpClientError as exc:
        logger.warning("MCP tool discovery failed on create: %s", exc)
        conn.discovered_tools = []
        conn.status = "error"

    db.add(conn)
    await db.flush()

    return _to_response(conn).model_dump(mode="json")


# ---------------------------------------------------------------------------
# POST /api/mcp/connections/{id}/test — ping
# ---------------------------------------------------------------------------


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> TestMcpResponse:
    conn = await _get_connection(db, connection_id, workspace_id)

    # Decrypt auth config for the ping
    auth_config = None
    if conn.auth_config_encrypted:
        auth_config = decrypt_json(conn.auth_config_encrypted)

    result = await ping_server(
        server_url=conn.server_url,
        auth_config=auth_config,
        auth_type=conn.auth_type,
    )

    # Update connection status
    conn.status = "active" if result["ok"] else "error"
    if result["ok"]:
        conn.last_verified_at = datetime.now(timezone.utc)

    return TestMcpResponse(**result)


# ---------------------------------------------------------------------------
# POST /api/mcp/connections/{id}/discover-tools — re-discover
# ---------------------------------------------------------------------------


@router.post("/connections/{connection_id}/discover-tools")
async def rediscover_tools(
    connection_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DiscoverToolsResponse:
    conn = await _get_connection(db, connection_id, workspace_id)

    # Decrypt auth config
    auth_config = None
    if conn.auth_config_encrypted:
        auth_config = decrypt_json(conn.auth_config_encrypted)

    try:
        tools = await discover_tools(
            server_url=conn.server_url,
            auth_config=auth_config,
            auth_type=conn.auth_type,
        )
        conn.discovered_tools = tools
        conn.status = "active"
        conn.last_verified_at = datetime.now(timezone.utc)
    except McpClientError as exc:
        logger.warning("MCP tool discovery failed: %s", exc)
        conn.status = "error"
        tools = []

    return DiscoverToolsResponse(
        tools=[McpToolItem(**t) for t in tools]
    )


# ---------------------------------------------------------------------------
# DELETE /api/mcp/connections/{id}
# ---------------------------------------------------------------------------


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    conn = await _get_connection(db, connection_id, workspace_id)
    await db.delete(conn)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(conn: McpConnection) -> McpConnectionItem:
    """Convert an McpConnection ORM object to the response schema."""
    tools = [
        McpToolItem(
            name=t.get("name", ""),
            description=t.get("description", ""),
            input_schema=t.get("input_schema", {}),
        )
        for t in (conn.discovered_tools or [])
    ]

    return McpConnectionItem(
        id=conn.id,
        name=conn.name,
        server_url=conn.server_url,
        auth_type=conn.auth_type,
        status=conn.status,
        discovered_tools=tools,
        last_verified_at=conn.last_verified_at,
        created_at=conn.created_at,
    )


async def _get_connection(
    db: AsyncSession, connection_id: str, workspace_id: str
) -> McpConnection:
    """Load an MCP connection or raise 404."""
    result = await db.execute(
        select(McpConnection).where(
            McpConnection.id == connection_id,
            McpConnection.workspace_id == workspace_id,
        )
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise not_found("mcp_connection", connection_id)
    return conn
