from fastapi import APIRouter, HTTPException

from app.core.agent_factory import get_agent_factory
from app.core.mcp_connection_store import get_mcp_connection_store
from app.models.mcp import (
    McpConnectionCreateRequest,
    McpConnectionResponse,
    McpConnectionUpdateRequest,
    McpTestResult,
    McpToolDescriptor,
)

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/connections", response_model=list[McpConnectionResponse])
def list_mcp_connections():
    return get_mcp_connection_store().list_connections()


@router.post("/connections", response_model=McpConnectionResponse)
def create_mcp_connection(body: McpConnectionCreateRequest):
    return get_mcp_connection_store().create_connection(body)


@router.patch("/connections/{connection_id}", response_model=McpConnectionResponse)
def update_mcp_connection(connection_id: str, body: McpConnectionUpdateRequest):
    try:
        return get_mcp_connection_store().update_connection(connection_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/connections/{connection_id}")
def delete_mcp_connection(connection_id: str):
    try:
        get_mcp_connection_store().delete_connection(connection_id)
        get_agent_factory().remove_mcp_connection_references(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.post("/connections/{connection_id}/test", response_model=McpTestResult)
def test_mcp_connection(connection_id: str):
    try:
        return get_mcp_connection_store().test_connection(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/connections/{connection_id}/discover-tools", response_model=list[McpToolDescriptor])
def discover_mcp_connection_tools(connection_id: str):
    try:
        return get_mcp_connection_store().discover_tools(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/connections/{connection_id}/tools", response_model=list[McpToolDescriptor])
def list_mcp_connection_tools(connection_id: str):
    try:
        return get_mcp_connection_store().list_tools(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
