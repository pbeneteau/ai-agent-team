"""Artifact-First API routes (Vision 2.0).

Endpoints:
  POST   /api/artifacts/sufficiency-check  — Smart Brief validation
  POST   /api/artifacts/                   — Create artifact + trigger Celery generation
  GET    /api/artifacts/{id}               — Get artifact with versions
  GET    /api/artifacts/{id}/diff           — Unified diff between two versions
  POST   /api/artifacts/{id}/iterate       — Add contextual comment + trigger next version
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.domain import (
    Artifact,
    ArtifactStatus,
    ArtifactVersion,
    ContextualComment,
    Project,
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SufficiencyRequest(BaseModel):
    title: str
    description: str


class HighlightItem(BaseModel):
    highlight_quote: str
    issue: str
    suggestion: str


class SufficiencyResponse(BaseModel):
    sufficient: bool
    highlights: list[HighlightItem]


class ArtifactCreateRequest(BaseModel):
    project_id: str
    title: str
    goal: Optional[str] = None


class ArtifactVersionResponse(BaseModel):
    id: str
    version_number: int
    s3_file_path: str
    token_cost: float
    created_at: str


class ArtifactResponse(BaseModel):
    id: str
    project_id: str
    title: str
    goal: Optional[str]
    status: str
    created_at: str
    versions: list[ArtifactVersionResponse]


class DiffResponse(BaseModel):
    old_version: int
    new_version: int
    diff: str


class IterateRequest(BaseModel):
    highlighted_text: Optional[str] = None
    instruction: str


class CommentResponse(BaseModel):
    id: str
    artifact_version_id: str
    highlighted_text: Optional[str]
    instruction: str
    resolved: bool
    created_at: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


# ---------------------------------------------------------------------------
# 1. Sufficiency check (from Phase 5)
# ---------------------------------------------------------------------------

@router.post("/sufficiency-check", response_model=SufficiencyResponse)
async def check_sufficiency(req: SufficiencyRequest):
    from app.core.task_sufficiency import analyze_sufficiency

    return await analyze_sufficiency(req.title, req.description)


# ---------------------------------------------------------------------------
# 2. Create artifact + trigger Celery task
# ---------------------------------------------------------------------------

@router.post("/", response_model=ArtifactResponse, status_code=201)
async def create_artifact(req: ArtifactCreateRequest, db: AsyncSession = Depends(get_db)):
    # Verify project exists
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    artifact = Artifact(
        project_id=req.project_id,
        title=req.title,
        goal=req.goal,
        status=ArtifactStatus.DRAFTING,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)

    # Trigger async generation via Celery
    from app.core.celery_app import generate_artifact

    generate_artifact.delay(artifact.id)

    return ArtifactResponse(
        id=artifact.id,
        project_id=artifact.project_id,
        title=artifact.title,
        goal=artifact.goal,
        status=artifact.status.value,
        created_at=artifact.created_at.isoformat(),
        versions=[],
    )


# ---------------------------------------------------------------------------
# 3. Get artifact with versions
# ---------------------------------------------------------------------------

@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(artifact_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Artifact)
        .options(selectinload(Artifact.versions))
        .where(Artifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    sorted_versions = sorted(artifact.versions, key=lambda v: v.version_number)

    return ArtifactResponse(
        id=artifact.id,
        project_id=artifact.project_id,
        title=artifact.title,
        goal=artifact.goal,
        status=artifact.status.value,
        created_at=artifact.created_at.isoformat(),
        versions=[
            ArtifactVersionResponse(
                id=v.id,
                version_number=v.version_number,
                s3_file_path=v.s3_file_path,
                token_cost=v.token_cost,
                created_at=v.created_at.isoformat(),
            )
            for v in sorted_versions
        ],
    )


# ---------------------------------------------------------------------------
# 4. Diff between two versions
# ---------------------------------------------------------------------------

@router.get("/{artifact_id}/diff", response_model=DiffResponse)
async def get_artifact_diff(
    artifact_id: str,
    v1: int,
    v2: int,
    db: AsyncSession = Depends(get_db),
):
    if v1 == v2:
        raise HTTPException(status_code=400, detail="v1 and v2 must be different")

    result = await db.execute(
        select(ArtifactVersion)
        .where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version_number.in_([v1, v2]),
        )
    )
    versions = {v.version_number: v for v in result.scalars().all()}

    if v1 not in versions:
        raise HTTPException(status_code=404, detail=f"Version {v1} not found")
    if v2 not in versions:
        raise HTTPException(status_code=404, detail=f"Version {v2} not found")

    from app.core.s3_workspace import S3WorkspaceManager

    s3 = S3WorkspaceManager()
    diff_text = await s3.get_artifact_diff(versions[v1].s3_file_path, versions[v2].s3_file_path)

    return DiffResponse(old_version=v1, new_version=v2, diff=diff_text)


# ---------------------------------------------------------------------------
# 5. Iterate: add contextual comment + trigger next version
# ---------------------------------------------------------------------------

@router.post("/{artifact_id}/iterate", response_model=CommentResponse, status_code=201)
async def iterate_artifact(
    artifact_id: str,
    req: IterateRequest,
    db: AsyncSession = Depends(get_db),
):
    # Verify artifact exists and is in review
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if artifact.status != ArtifactStatus.IN_REVIEW:
        raise HTTPException(status_code=400, detail="Artifact must be in review status to iterate")

    # Find the latest version
    max_v_result = await db.execute(
        select(func.max(ArtifactVersion.version_number))
        .where(ArtifactVersion.artifact_id == artifact_id)
    )
    max_v = max_v_result.scalar()
    if max_v is None:
        raise HTTPException(status_code=400, detail="No versions exist yet — cannot iterate")

    # Get the latest version row for the comment FK
    latest_result = await db.execute(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version_number == max_v,
        )
    )
    latest_version = latest_result.scalar_one()

    # Create the contextual comment
    comment = ContextualComment(
        artifact_version_id=latest_version.id,
        highlighted_text=req.highlighted_text,
        instruction=req.instruction,
    )
    db.add(comment)

    # Flip artifact back to DRAFTING for the next generation pass
    artifact.status = ArtifactStatus.DRAFTING
    await db.commit()
    await db.refresh(comment)

    # Trigger Celery task for the next version
    from app.core.celery_app import generate_artifact

    generate_artifact.delay(artifact_id)

    return CommentResponse(
        id=comment.id,
        artifact_version_id=comment.artifact_version_id,
        highlighted_text=comment.highlighted_text,
        instruction=comment.instruction,
        resolved=comment.resolved,
        created_at=comment.created_at.isoformat(),
    )
