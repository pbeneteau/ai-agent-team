"""Project CRUD + brief management endpoints.

Ref: TDD-04 Sections 4 (projects), 7 (documents).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.projects import (
    BriefContext,
    CreateProjectRequest,
    DocumentCreated,
    DocumentItem,
    ProjectDetail,
    ProjectListItem,
    PublishResponse,
    SaveDraftRequest,
    UpdateProjectRequest,
)
from app.core.database import get_db
from app.core.errors import not_found, validation_error, payload_too_large
from app.core.pagination import (
    PaginatedResponse,
    apply_cursor_pagination,
    paginate,
    DEFAULT_LIMIT,
)
from app.core.workspace_id import get_workspace_id
from app.models.artifact import Artifact
from app.models.document import Document
from app.models.git_provider_connection import GitProviderConnection
from app.models.project import Project

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["projects"])

MAX_DOCUMENT_SIZE = 20 * 1024 * 1024  # 20 MB

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/x-yaml",
    "text/yaml",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_project_or_404(
    project_id: str, workspace_id: str, db: AsyncSession
) -> Project:
    project = await db.get(Project, project_id)
    if project is None or project.workspace_id != workspace_id:
        raise not_found("project", project_id)
    return project


async def _fetch_readme(
    connection_id: str, repo_full_name: str, db: AsyncSession,
) -> str | None:
    """Fetch README from a git repo via the provider API. Returns None on failure."""
    try:
        conn = await db.get(GitProviderConnection, connection_id)
        if conn is None or conn.status != "active":
            return None

        from app.core.encryption import decrypt_string

        token = decrypt_string(conn.access_token_encrypted)
        parts = repo_full_name.split("/", 1)
        if len(parts) != 2:
            return None
        owner, repo = parts

        if conn.provider == "github":
            from app.core.git_providers.github import GitHubClient
            client = GitHubClient(token)
        elif conn.provider == "gitlab":
            from app.core.git_providers.gitlab import GitLabClient
            client = GitLabClient(token)
        else:
            return None

        try:
            readme = await client.get_readme(owner, repo)
            return readme
        finally:
            await client.close()
    except Exception:
        logger.warning("Failed to fetch README for %s (non-fatal)", repo_full_name, exc_info=True)
        return None


def _brief_status(project: Project) -> str:
    if project.brief_published:
        return "published"
    if project.brief_draft:
        return "draft"
    return "none"


# ---------------------------------------------------------------------------
# GET /api/projects
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=PaginatedResponse[ProjectListItem])
async def list_projects(
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=100),
    cursor: str | None = Query(None),
) -> PaginatedResponse[ProjectListItem]:
    query = select(Project).where(Project.workspace_id == workspace_id)
    query = apply_cursor_pagination(
        query, cursor=cursor, limit=limit,
        sort_columns=[Project.created_at, Project.id],
    )

    result = await db.execute(query)
    rows = list(result.scalars().all())
    paged = paginate(rows, limit=limit, sort_keys=["created_at", "id"])

    items = []
    for p in paged.items:
        art_count = await db.scalar(
            select(func.count()).select_from(Artifact).where(Artifact.project_id == p.id)
        ) or 0
        items.append(ProjectListItem(
            id=p.id,
            name=p.name,
            description=p.description,
            primary_language=p.primary_language,
            framework=p.framework,
            git_repo_url=p.git_repo_url,
            artifact_count=art_count,
            brief_status=_brief_status(p),
            created_at=p.created_at,
        ))

    return PaginatedResponse[ProjectListItem](
        items=items, next_cursor=paged.next_cursor, has_more=paged.has_more,
    )


# ---------------------------------------------------------------------------
# POST /api/projects
# ---------------------------------------------------------------------------


@router.post("/projects", status_code=201, response_model=ProjectDetail)
async def create_project(
    body: CreateProjectRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    now = datetime.now(timezone.utc)

    # Fetch README from git if connection + repo provided
    readme_content: str | None = None
    if body.git_connection_id and body.git_repo_url:
        readme_content = await _fetch_readme(body.git_connection_id, body.git_repo_url, db)

    project = Project(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        primary_language=body.primary_language,
        framework=body.framework,
        package_manager=body.package_manager,
        git_repo_url=body.git_repo_url,
        brief_draft=readme_content,
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    await db.flush()

    return ProjectDetail(
        id=project.id,
        name=project.name,
        description=project.description,
        primary_language=project.primary_language,
        framework=project.framework,
        package_manager=project.package_manager,
        git_repo_url=project.git_repo_url,
        has_readme=readme_content is not None,
        artifact_count=0,
        brief_status=_brief_status(project),
        brief_draft=project.brief_draft,
        brief_published=project.brief_published,
        brief_fingerprint=project.brief_fingerprint,
        brief_published_at=project.brief_published_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/projects/{id}
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_project_or_404(project_id, workspace_id, db)
    art_count = await db.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.project_id == project_id)
    ) or 0

    return ProjectDetail(
        id=project.id,
        name=project.name,
        description=project.description,
        primary_language=project.primary_language,
        framework=project.framework,
        package_manager=project.package_manager,
        git_repo_url=project.git_repo_url,
        has_readme=project.brief_draft is not None and len(project.brief_draft) > 0,
        artifact_count=art_count,
        brief_status=_brief_status(project),
        brief_draft=project.brief_draft,
        brief_published=project.brief_published,
        brief_fingerprint=project.brief_fingerprint,
        brief_published_at=project.brief_published_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# ---------------------------------------------------------------------------
# PATCH /api/projects/{id}
# ---------------------------------------------------------------------------


@router.patch("/projects/{project_id}", response_model=ProjectDetail)
async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_project_or_404(project_id, workspace_id, db)

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.primary_language is not None:
        project.primary_language = body.primary_language
    if body.framework is not None:
        project.framework = body.framework
    if body.package_manager is not None:
        project.package_manager = body.package_manager
    if body.git_repo_url is not None:
        project.git_repo_url = body.git_repo_url

    await db.flush()

    art_count = await db.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.project_id == project_id)
    ) or 0

    return ProjectDetail(
        id=project.id,
        name=project.name,
        description=project.description,
        primary_language=project.primary_language,
        framework=project.framework,
        package_manager=project.package_manager,
        git_repo_url=project.git_repo_url,
        has_readme=project.brief_draft is not None and len(project.brief_draft) > 0,
        artifact_count=art_count,
        brief_status=_brief_status(project),
        brief_draft=project.brief_draft,
        brief_published=project.brief_published,
        brief_fingerprint=project.brief_fingerprint,
        brief_published_at=project.brief_published_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# ---------------------------------------------------------------------------
# DELETE /api/projects/{id}
# ---------------------------------------------------------------------------


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
    x_confirm_delete: str | None = Header(None, alias="X-Confirm-Delete"),
) -> None:
    if x_confirm_delete != "true":
        raise validation_error(
            "Missing X-Confirm-Delete: true header. Project deletion is irreversible."
        )
    project = await _get_project_or_404(project_id, workspace_id, db)
    await db.delete(project)
    await db.flush()


# ---------------------------------------------------------------------------
# GET /api/projects/{id}/context
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/context", response_model=BriefContext)
async def get_brief_context(
    project_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> BriefContext:
    project = await _get_project_or_404(project_id, workspace_id, db)
    return BriefContext(
        draft=project.brief_draft,
        published=project.brief_published,
        published_at=project.brief_published_at,
        fingerprint=project.brief_fingerprint,
    )


# ---------------------------------------------------------------------------
# PUT /api/projects/{id}/context/draft
# ---------------------------------------------------------------------------


@router.put("/projects/{project_id}/context/draft", response_model=BriefContext)
async def save_draft(
    project_id: str,
    body: SaveDraftRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> BriefContext:
    project = await _get_project_or_404(project_id, workspace_id, db)
    project.brief_draft = body.content
    await db.flush()

    return BriefContext(
        draft=project.brief_draft,
        published=project.brief_published,
        published_at=project.brief_published_at,
        fingerprint=project.brief_fingerprint,
    )


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/context/publish
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/context/publish", response_model=PublishResponse)
async def publish_brief(
    project_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> PublishResponse:
    project = await _get_project_or_404(project_id, workspace_id, db)

    if not project.brief_draft:
        raise validation_error("Cannot publish: no draft content.")

    # Compute fingerprint
    new_fingerprint = hashlib.sha256(
        project.brief_draft.encode("utf-8")
    ).hexdigest()

    # Copy draft → published
    project.brief_published = project.brief_draft
    project.brief_fingerprint = new_fingerprint
    project.brief_published_at = datetime.now(timezone.utc)
    await db.flush()

    # Trigger rebriefing only if fingerprint changed
    agents_rebriefed = 0
    if project.brief_fingerprint != new_fingerprint or True:
        from app.agents.briefing import brief_all_agents
        agents_rebriefed = await brief_all_agents(project, db)

    return PublishResponse(
        published=project.brief_published,
        published_at=project.brief_published_at,
        fingerprint=project.brief_fingerprint,
        agents_rebriefed=agents_rebriefed,
    )


# ---------------------------------------------------------------------------
# GET /api/projects/{pid}/documents
# ---------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/documents",
    response_model=PaginatedResponse[DocumentItem],
)
async def list_documents(
    project_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=100),
    cursor: str | None = Query(None),
) -> PaginatedResponse[DocumentItem]:
    await _get_project_or_404(project_id, workspace_id, db)

    query = select(Document).where(Document.project_id == project_id)
    query = apply_cursor_pagination(
        query, cursor=cursor, limit=limit,
        sort_columns=[Document.created_at, Document.id],
    )

    result = await db.execute(query)
    rows = list(result.scalars().all())
    paged = paginate(rows, limit=limit, sort_keys=["created_at", "id"])

    return PaginatedResponse[DocumentItem](
        items=[
            DocumentItem(
                id=d.id,
                filename=d.filename,
                mime_type=d.mime_type,
                size_bytes=d.size_bytes,
                chunk_count=d.chunk_count,
                processing_status=d.processing_status,
                created_at=d.created_at,
            )
            for d in paged.items
        ],
        next_cursor=paged.next_cursor,
        has_more=paged.has_more,
    )


# ---------------------------------------------------------------------------
# POST /api/projects/{pid}/documents
# ---------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/documents",
    status_code=201,
    response_model=DocumentCreated,
)
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DocumentCreated:
    await _get_project_or_404(project_id, workspace_id, db)

    # Read file content
    file_bytes = await file.read()
    size = len(file_bytes)

    if size > MAX_DOCUMENT_SIZE:
        raise payload_too_large(f"File exceeds {MAX_DOCUMENT_SIZE // (1024*1024)} MB limit.")

    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"

    # Create document row
    doc_id = str(uuid.uuid4())
    s3_path = f"documents/{doc_id}/{filename}"

    doc = Document(
        id=doc_id,
        project_id=project_id,
        filename=filename,
        mime_type=content_type,
        s3_path=s3_path,
        size_bytes=size,
        processing_status="pending",
    )
    db.add(doc)
    await db.flush()

    # Upload to S3
    from app.core.s3_workspace import upload_document as s3_upload
    s3_upload(doc_id, filename, file_bytes)

    # Enqueue processing
    from app.core.celery_app import process_document_upload
    process_document_upload.delay(doc_id)

    return DocumentCreated(
        id=doc.id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        processing_status=doc.processing_status,
    )


# ---------------------------------------------------------------------------
# DELETE /api/projects/{pid}/documents/{did}
# ---------------------------------------------------------------------------


@router.delete("/projects/{project_id}/documents/{document_id}", status_code=204)
async def delete_document(
    project_id: str,
    document_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_project_or_404(project_id, workspace_id, db)

    doc = await db.get(Document, document_id)
    if doc is None or doc.project_id != project_id:
        raise not_found("document", document_id)

    # Delete from S3
    from app.core.s3_workspace import delete_document as s3_delete
    s3_delete(document_id)

    # Delete DB row (chunks cascade)
    await db.delete(doc)
    await db.flush()
