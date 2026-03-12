from fastapi import APIRouter, HTTPException

from app.core.agent_factory import get_agent_factory
from app.core.git_provider_store import get_git_provider_store
from app.models.git_providers import (
    GitProviderConnectionCreateRequest,
    GitProviderConnectionResponse,
    GitProviderConnectionUpdateRequest,
    GitProviderTestResult,
    GitRemoteRepo,
)

router = APIRouter(prefix="/git-providers", tags=["git-providers"])


@router.get("/connections", response_model=list[GitProviderConnectionResponse])
def list_git_provider_connections():
    return get_git_provider_store().list_connections()


@router.post("/connections", response_model=GitProviderConnectionResponse)
def create_git_provider_connection(body: GitProviderConnectionCreateRequest):
    return get_git_provider_store().create_connection(body)


@router.patch("/connections/{connection_id}", response_model=GitProviderConnectionResponse)
def update_git_provider_connection(connection_id: str, body: GitProviderConnectionUpdateRequest):
    try:
        return get_git_provider_store().update_connection(connection_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/connections/{connection_id}")
def delete_git_provider_connection(connection_id: str):
    try:
        get_git_provider_store().delete_connection(connection_id)
        get_agent_factory().remove_git_provider_connection_references(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.post("/connections/{connection_id}/test", response_model=GitProviderTestResult)
def test_git_provider_connection(connection_id: str):
    try:
        return get_git_provider_store().test_connection(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/connections/{connection_id}/repos", response_model=list[GitRemoteRepo])
def list_git_provider_repos(connection_id: str):
    try:
        return get_git_provider_store().list_repos(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/connections/{connection_id}/repos/refresh", response_model=list[GitRemoteRepo])
def refresh_git_provider_repos(connection_id: str):
    try:
        return get_git_provider_store().refresh_repos(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
