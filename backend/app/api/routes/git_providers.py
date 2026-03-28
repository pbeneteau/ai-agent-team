"""Git provider connection CRUD endpoints.

Ref: TDD-04 Section 8 (CRUD), Section 9 (push flow).
AD-14: PAT stored encrypted, never logged or returned.
AD-17: Auto-configure webhooks via API.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.git_providers import (
    CreateGitConnectionRequest,
    GitConnectionItem,
    RepoItem,
    RepoListResponse,
    TestConnectionResponse,
    WebhookConfiguredResponse,
)
from app.config.settings import settings
from app.core.database import get_db
from app.core.encryption import decrypt_string, encrypt_string
from app.core.errors import not_found, validation_error
from app.core.git_providers import get_client
from app.core.git_providers.common import GitProviderError
from app.core.workspace_id import get_workspace_id
from app.models.git_provider_connection import GitProviderConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/git-providers", tags=["git-providers"])


# ---------------------------------------------------------------------------
# GET /api/git-providers/connections — list
# ---------------------------------------------------------------------------


@router.get("/connections")
async def list_connections(
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(GitProviderConnection)
        .where(GitProviderConnection.workspace_id == workspace_id)
        .order_by(GitProviderConnection.created_at.desc())
    )
    connections = result.scalars().all()

    items = [
        GitConnectionItem(
            id=c.id,
            provider=c.provider,
            display_name=c.display_name,
            status=c.status,
            repositories=c.repositories or [],
            last_verified_at=c.last_verified_at,
            created_at=c.created_at,
        ).model_dump(mode="json")
        for c in connections
    ]

    return {"items": items}


# ---------------------------------------------------------------------------
# POST /api/git-providers/connections — create
# ---------------------------------------------------------------------------


@router.post("/connections", status_code=201)
async def create_connection(
    body: CreateGitConnectionRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # 1. Validate token by calling provider API
    client = get_client(body.provider, body.access_token)
    try:
        user_info = await client.validate_token()
    except GitProviderError as exc:
        raise validation_error(
            f"Invalid {body.provider} token: {exc}",
            details={"provider": body.provider},
        )
    finally:
        await client.close()

    # 2. List repos to populate the repositories JSONB
    client = get_client(body.provider, body.access_token)
    try:
        repos = await client.list_repos()
    except GitProviderError:
        repos = []
    finally:
        await client.close()

    repo_data = [
        {
            "owner": r.owner,
            "name": r.name,
            "full_name": r.full_name,
            "default_branch": r.default_branch,
            "webhook_configured": False,
        }
        for r in repos
    ]

    # 3. Encrypt token and store
    connection = GitProviderConnection(
        workspace_id=workspace_id,
        provider=body.provider,
        display_name=body.display_name,
        access_token_encrypted=encrypt_string(body.access_token),
        repositories=repo_data,
        status="active",
        last_verified_at=datetime.now(timezone.utc),
    )
    db.add(connection)
    await db.flush()

    return GitConnectionItem(
        id=connection.id,
        provider=connection.provider,
        display_name=connection.display_name,
        status=connection.status,
        repositories=connection.repositories,
        last_verified_at=connection.last_verified_at,
        created_at=connection.created_at,
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# POST /api/git-providers/connections/{id}/test — test
# ---------------------------------------------------------------------------


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> TestConnectionResponse:
    conn = await _get_connection(db, connection_id, workspace_id)
    token = decrypt_string(conn.access_token_encrypted)

    client = get_client(conn.provider, token)
    try:
        user_info = await client.validate_token()
    except GitProviderError as exc:
        conn.status = "error"
        return TestConnectionResponse(ok=False, user="", scopes=[])
    finally:
        await client.close()

    conn.status = "active"
    conn.last_verified_at = datetime.now(timezone.utc)

    return TestConnectionResponse(
        ok=True,
        user=user_info.username,
        scopes=user_info.scopes,
        rate_limit_remaining=user_info.rate_limit_remaining,
    )


# ---------------------------------------------------------------------------
# GET /api/git-providers/connections/{id}/repos — list repos
# ---------------------------------------------------------------------------


@router.get("/connections/{connection_id}/repos")
async def list_repos(
    connection_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> RepoListResponse:
    conn = await _get_connection(db, connection_id, workspace_id)
    token = decrypt_string(conn.access_token_encrypted)

    client = get_client(conn.provider, token)
    try:
        repos = await client.list_repos()
    except GitProviderError as exc:
        raise validation_error(f"Failed to list repos: {exc}")
    finally:
        await client.close()

    # Merge webhook_configured status from stored data
    configured_repos: set[str] = set()
    for r in (conn.repositories or []):
        if r.get("webhook_configured"):
            configured_repos.add(f"{r['owner']}/{r['name']}")

    items = [
        RepoItem(
            owner=r.owner,
            name=r.name,
            full_name=r.full_name,
            default_branch=r.default_branch,
            private=r.private,
            webhook_configured=r.full_name in configured_repos,
        )
        for r in repos
    ]

    # Update stored repos
    conn.repositories = [item.model_dump() for item in items]

    return RepoListResponse(items=items)


# ---------------------------------------------------------------------------
# POST /api/git-providers/connections/{id}/repos/{owner}/{repo}/webhook
# ---------------------------------------------------------------------------


@router.post("/connections/{connection_id}/repos/{owner}/{repo}/webhook")
async def configure_webhook(
    connection_id: str,
    owner: str,
    repo: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> WebhookConfiguredResponse:
    conn = await _get_connection(db, connection_id, workspace_id)
    token = decrypt_string(conn.access_token_encrypted)

    # Generate webhook secret
    webhook_secret = secrets.token_hex(32)

    # Determine webhook URL based on provider
    provider_path = "github" if conn.provider == "github" else "gitlab"
    webhook_url = f"{settings.WEBHOOK_BASE_URL}/api/webhooks/{provider_path}"

    client = get_client(conn.provider, token)
    try:
        wh_info = await client.create_webhook(
            owner=owner,
            repo=repo,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
    except GitProviderError as exc:
        raise validation_error(
            f"Failed to configure webhook: {exc}",
            details={"owner": owner, "repo": repo},
        )
    finally:
        await client.close()

    # Store webhook secret on connection
    conn.webhook_secret = webhook_secret

    # Mark repo as webhook_configured in repositories JSONB
    repos = list(conn.repositories or [])
    for r in repos:
        if r.get("owner") == owner and r.get("name") == repo:
            r["webhook_configured"] = True
            r["webhook_id"] = wh_info.webhook_id
            break
    else:
        repos.append({
            "owner": owner,
            "name": repo,
            "webhook_configured": True,
            "webhook_id": wh_info.webhook_id,
        })
    conn.repositories = repos

    return WebhookConfiguredResponse(
        webhook_id=wh_info.webhook_id,
        webhook_url=wh_info.webhook_url,
        events=wh_info.events,
        status=wh_info.status,
    )


# ---------------------------------------------------------------------------
# DELETE /api/git-providers/connections/{id}
# ---------------------------------------------------------------------------


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    conn = await _get_connection(db, connection_id, workspace_id)
    token = decrypt_string(conn.access_token_encrypted)

    # Best-effort: remove configured webhooks
    client = get_client(conn.provider, token)
    try:
        for r in (conn.repositories or []):
            if r.get("webhook_configured") and r.get("webhook_id"):
                try:
                    await client.delete_webhook(
                        owner=r["owner"],
                        repo=r["name"],
                        webhook_id=r["webhook_id"],
                    )
                except Exception:
                    logger.warning(
                        "Failed to delete webhook %s on %s/%s (best-effort)",
                        r.get("webhook_id"), r.get("owner"), r.get("name"),
                    )
    finally:
        await client.close()

    await db.delete(conn)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_connection(
    db: AsyncSession, connection_id: str, workspace_id: str
) -> GitProviderConnection:
    """Load a connection or raise 404."""
    result = await db.execute(
        select(GitProviderConnection).where(
            GitProviderConnection.id == connection_id,
            GitProviderConnection.workspace_id == workspace_id,
        )
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise not_found("git_provider_connection", connection_id)
    return conn
