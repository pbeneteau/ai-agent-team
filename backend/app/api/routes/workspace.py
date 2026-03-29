"""Workspace settings endpoints — GET/PATCH workspace context + document management.

Ref: TDD-04 Section 2 (extended).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.workspace import (
    WorkspaceDetail,
    WorkspaceDocumentItem,
    WorkspaceUpdateRequest,
)
from app.core.database import get_db
from app.core.errors import not_found, payload_too_large
from app.core.pagination import PaginatedResponse
from app.core.workspace_id import get_workspace_id
from app.models.agent import Agent
from app.models.document import Document
from app.models.workspace import Workspace

# Fields that meaningfully affect agent knowledge — changing these re-triggers learning
CONTEXT_FIELDS = {
    "domain_description", "product_description", "target_audience",
    "main_goals", "existing_team", "tech_stack", "company_stage",
}

router = APIRouter(prefix="/api", tags=["workspace"])

MAX_DOCUMENT_SIZE = 20 * 1024 * 1024  # 20 MB


def _to_detail(w: Workspace) -> WorkspaceDetail:
    return WorkspaceDetail(
        id=w.id,
        name=w.name,
        domain_description=w.domain_description,
        product_description=w.product_description,
        tech_stack=w.tech_stack,
        company_stage=w.company_stage,
        target_audience=w.target_audience,
        main_goals=w.main_goals,
        existing_team=w.existing_team,
        team_size=None,
        monthly_budget_usd=float(w.monthly_budget_usd),
        monthly_spend_usd=float(w.monthly_spend_usd),
        onboarding_completed=w.onboarding_completed,
        created_at=w.created_at,
    )


# ---------------------------------------------------------------------------
# GET /api/workspace
# ---------------------------------------------------------------------------


@router.get("/workspace", response_model=WorkspaceDetail)
async def get_workspace(
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceDetail:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise not_found("workspace", workspace_id)
    return _to_detail(workspace)


# ---------------------------------------------------------------------------
# PATCH /api/workspace
# ---------------------------------------------------------------------------


@router.patch("/workspace", response_model=WorkspaceDetail)
async def update_workspace(
    body: WorkspaceUpdateRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceDetail:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise not_found("workspace", workspace_id)

    updated_fields = set(body.model_dump(exclude_unset=True).keys())
    for field, value in body.model_dump(exclude_unset=True).items():
        if field != "team_size":  # team_size is not stored on workspace
            setattr(workspace, field, value)

    await db.flush()

    # Re-trigger learning for all active agents when meaningful context changes
    if updated_fields & CONTEXT_FIELDS:
        result = await db.execute(
            select(Agent).where(
                Agent.workspace_id == workspace_id,
                Agent.archived_at.is_(None),
            )
        )
        agents = result.scalars().all()

        if agents:
            # Existing roster — re-trigger learning for ready/learning agents
            from app.core.celery_app import execute_agent_learning
            for agent in agents:
                if agent.status in ("ready", "learning"):
                    execute_agent_learning.delay(agent.id)
        else:
            # No agents at all — generate a fresh roster from current workspace context
            from app.api.routes.onboarding import _generate_roster
            from app.core.celery_app import execute_agent_learning
            import uuid as _uuid
            from datetime import datetime, timezone

            roster_specs = await _generate_roster(
                company_name=workspace.name or "",
                domain_description=workspace.domain_description or "",
                product_description=workspace.product_description,
                tech_stack=workspace.tech_stack,
                company_stage=workspace.company_stage,
                target_audience=workspace.target_audience,
                main_goals=workspace.main_goals,
                existing_team=workspace.existing_team,
                use_case="both",
            )
            now = datetime.now(timezone.utc)
            for spec in roster_specs:
                agent = Agent(
                    id=str(_uuid.uuid4()),
                    workspace_id=workspace_id,
                    name=spec["name"],
                    specialization=spec["specialization"],
                    status="learning",
                    readiness_score=0,
                    progression_level="apprenti",
                    model_tier="sonnet",
                    completed_artifacts=0,
                    tools=[],
                    created_at=now,
                    updated_at=now,
                )
                db.add(agent)
                await db.flush()
                execute_agent_learning.delay(agent.id)

    return _to_detail(workspace)


# ---------------------------------------------------------------------------
# GET /api/workspace/documents
# ---------------------------------------------------------------------------


@router.get("/workspace/documents", response_model=PaginatedResponse[WorkspaceDocumentItem])
async def list_workspace_documents(
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[WorkspaceDocumentItem]:
    q = (
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(q)
    docs = result.scalars().all()
    items = [
        WorkspaceDocumentItem(
            id=d.id,
            filename=d.filename,
            mime_type=d.mime_type,
            size_bytes=d.size_bytes,
            processing_status=d.processing_status,
            created_at=d.created_at,
        )
        for d in docs
    ]
    return PaginatedResponse(items=items, next_cursor=None, has_more=False)


# ---------------------------------------------------------------------------
# POST /api/workspace/documents
# ---------------------------------------------------------------------------


@router.post("/workspace/documents", status_code=201, response_model=WorkspaceDocumentItem)
async def upload_workspace_document(
    file: UploadFile = File(...),
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceDocumentItem:
    file_bytes = await file.read()
    size = len(file_bytes)

    if size > MAX_DOCUMENT_SIZE:
        raise payload_too_large(f"File exceeds {MAX_DOCUMENT_SIZE // (1024 * 1024)} MB limit.")

    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    doc_id = str(uuid.uuid4())
    s3_path = f"documents/{doc_id}/{filename}"

    doc = Document(
        id=doc_id,
        workspace_id=workspace_id,
        filename=filename,
        mime_type=content_type,
        s3_path=s3_path,
        size_bytes=size,
        processing_status="pending",
    )
    db.add(doc)
    await db.flush()

    from app.core.s3_workspace import upload_document as s3_upload
    s3_upload(doc_id, filename, file_bytes)

    from app.core.celery_app import process_document_upload
    process_document_upload.delay(doc_id)

    return WorkspaceDocumentItem(
        id=doc.id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        processing_status=doc.processing_status,
        created_at=doc.created_at,
    )


# ---------------------------------------------------------------------------
# DELETE /api/workspace/documents/{doc_id}
# ---------------------------------------------------------------------------


@router.delete("/workspace/documents/{document_id}", status_code=204)
async def delete_workspace_document(
    document_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    doc = await db.get(Document, document_id)
    if doc is None or doc.workspace_id != workspace_id:
        raise not_found("document", document_id)

    from app.core.s3_workspace import delete_document as s3_delete
    try:
        s3_delete(doc.id, doc.filename)
    except Exception:
        pass

    await db.delete(doc)
    await db.flush()
