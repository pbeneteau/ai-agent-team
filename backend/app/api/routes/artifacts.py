"""Artifact lifecycle endpoints — the core of the product.

Ref: TDD-04 Section 5 (artifact endpoints — all 12).
     TDD-04 Section 6 (standalone sufficiency check).
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.artifacts import (
    ApproveResponse,
    ArtifactListItem,
    ArtifactResponse,
    ArtifactStatusResponse,
    CancelResponse,
    CreateArtifactRequest,
    DelegateConfirmResponse,
    DelegatePlan,
    DelegatePreviewResponse,
    DelegateRequest,
    ExecutionStatus,
    IterateRequest,
    IterateResponse,
    RetryResponse,
    StandaloneSufficiencyRequest,
    SufficiencyIssueSchema,
    SufficiencyResponse,
    VersionItem,
    WaveAgentInfo,
    WavePlanInfo,
)
from app.core.database import get_db
from app.core.errors import (
    budget_exceeded,
    not_found,
    validation_error,
)
from app.core.pagination import (
    PaginatedResponse,
    apply_cursor_pagination,
    paginate,
    DEFAULT_LIMIT,
)
from app.core.workspace_id import get_workspace_id
from app.models.agent import Agent
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.contextual_comment import ContextualComment
from app.models.execution_wave import ExecutionWave
from app.models.project import Project
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["artifacts"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_artifact_or_404(
    artifact_id: str, db: AsyncSession
) -> Artifact:
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise not_found("artifact", artifact_id)
    return artifact


def _artifact_to_response(artifact: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact.id,
        project_id=artifact.project_id,
        artifact_type=artifact.artifact_type,
        title=artifact.title,
        goal=artifact.goal,
        target_audience=artifact.target_audience,
        context=artifact.context,
        description=artifact.description,
        status=artifact.status,
        max_budget_usd=float(artifact.max_budget_usd),
        total_cost_usd=float(artifact.total_cost_usd),
        current_version=artifact.current_version,
        git_repo_url=artifact.git_repo_url,
        git_base_branch=artifact.git_base_branch,
        git_feature_branch=artifact.git_feature_branch,
        git_pr_url=artifact.git_pr_url,
        git_pr_number=artifact.git_pr_number,
        approved_at=artifact.approved_at,
        cancelled_at=artifact.cancelled_at,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def _build_delegate_plan(routing_result: "RoutingResult") -> DelegatePlan:
    """Convert a RoutingResult into the API response shape."""
    from app.agents.dag_templates import get_template

    template = get_template(routing_result.template_key)
    waves = []
    for wave_info in routing_result.dag_plan.get("waves", []):
        agents = []
        for slot in wave_info.get("slots", []):
            agents.append(WaveAgentInfo(
                slot_id=slot.get("slot_id", ""),
                agent_id=slot.get("agent_id"),
                agent_name=slot.get("agent_name"),
            ))
        waves.append(WavePlanInfo(
            wave_number=wave_info.get("wave_number", 0),
            label=wave_info.get("label", ""),
            agents=agents,
        ))

    return DelegatePlan(
        template_id=routing_result.template_key,
        template_name=template.name,
        waves=waves,
        estimated_cost_usd=float(routing_result.estimated_cost),
        estimated_waves=len(waves),
    )


# ---------------------------------------------------------------------------
# POST /api/artifacts — create
# ---------------------------------------------------------------------------


@router.post("/artifacts", status_code=201, response_model=ArtifactResponse)
async def create_artifact(
    body: CreateArtifactRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    # Verify project exists
    project = await db.get(Project, body.project_id)
    if project is None or project.workspace_id != workspace_id:
        raise not_found("project", body.project_id)

    now = datetime.now(timezone.utc)
    artifact = Artifact(
        id=str(uuid.uuid4()),
        project_id=body.project_id,
        artifact_type=body.artifact_type,
        title=body.title,
        goal=body.goal,
        target_audience=body.target_audience,
        context=body.context,
        description=body.description,
        status="drafting",
        max_budget_usd=body.max_budget_usd,
        total_cost_usd=0.0,
        current_version=0,
        git_repo_url=body.git_repo_url,
        git_base_branch=body.git_base_branch,
        created_at=now,
        updated_at=now,
    )
    db.add(artifact)
    await db.flush()

    return _artifact_to_response(artifact)


# ---------------------------------------------------------------------------
# POST /api/artifacts/{id}/validate — sufficiency check
# ---------------------------------------------------------------------------


@router.post("/artifacts/{artifact_id}/validate", response_model=SufficiencyResponse)
async def validate_artifact(
    artifact_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> SufficiencyResponse:
    artifact = await _get_artifact_or_404(artifact_id, db)

    # Load workspace for sufficiency check
    project = await db.get(Project, artifact.project_id)
    workspace = await db.get(Workspace, workspace_id)

    from app.agents.sufficiency import run_sufficiency_check
    result = await run_sufficiency_check(artifact, workspace)

    return SufficiencyResponse(
        eligible=result.eligible,
        score=result.score,
        issues=[
            SufficiencyIssueSchema(
                severity=i.severity,
                field=i.field,
                matched_text=i.matched_text,
                issue=i.issue,
                suggestion=i.suggestion,
            )
            for i in result.issues
        ],
    )


# ---------------------------------------------------------------------------
# POST /api/artifacts/{id}/delegate — preview or confirm execution
# ---------------------------------------------------------------------------


@router.post("/artifacts/{artifact_id}/delegate")
async def delegate_artifact(
    artifact_id: str,
    body: DelegateRequest = DelegateRequest(),
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DelegatePreviewResponse | DelegateConfirmResponse:
    artifact = await _get_artifact_or_404(artifact_id, db)

    # Check monthly budget
    workspace = await db.get(Workspace, workspace_id)
    if workspace and float(workspace.monthly_spend_usd) >= float(workspace.monthly_budget_usd):
        raise budget_exceeded("Monthly budget ceiling reached.")

    # Route the brief
    result = await db.execute(
        select(Agent)
        .where(Agent.workspace_id == workspace_id)
        .where(Agent.archived_at.is_(None))
    )
    roster_agents = result.scalars().all()

    from app.agents.router import route_brief
    routing_result = await route_brief(artifact, roster_agents)
    plan = _build_delegate_plan(routing_result)

    if not body.confirm:
        return DelegatePreviewResponse(plan=plan)

    # Confirm mode: create execution wave and enqueue
    wave = ExecutionWave(
        id=str(uuid.uuid4()),
        artifact_id=artifact_id,
        trigger="initial",
        dag_plan=routing_result.dag_plan,
        assembled_team=[t for t in routing_result.assembled_team],
        status="queued",
        total_steps=len(routing_result.step_labels),
        step_labels=routing_result.step_labels,
    )
    db.add(wave)

    artifact.status = "drafting"
    await db.flush()

    from app.core.celery_app import execute_artifact_dag
    execute_artifact_dag.delay(wave.id)

    return DelegateConfirmResponse(
        artifact_id=artifact.id,
        status=artifact.status,
        execution_wave_id=wave.id,
        plan=plan,
    )


# ---------------------------------------------------------------------------
# GET /api/artifacts/{id} — detail
# ---------------------------------------------------------------------------


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    artifact = await _get_artifact_or_404(artifact_id, db)
    return _artifact_to_response(artifact)


# ---------------------------------------------------------------------------
# GET /api/artifacts/{id}/status — lightweight heartbeat
# ---------------------------------------------------------------------------


@router.get("/artifacts/{artifact_id}/status", response_model=ArtifactStatusResponse)
async def artifact_status(
    artifact_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ArtifactStatusResponse:
    artifact = await _get_artifact_or_404(artifact_id, db)

    execution = None
    if artifact.status == "drafting":
        # Find the latest active wave
        result = await db.execute(
            select(ExecutionWave)
            .where(ExecutionWave.artifact_id == artifact_id)
            .where(ExecutionWave.status.in_(["queued", "running"]))
            .order_by(ExecutionWave.created_at.desc())
            .limit(1)
        )
        wave = result.scalar_one_or_none()
        if wave:
            estimated_remaining: int | None = None
            if (
                wave.started_at is not None
                and wave.current_step > 0
                and wave.total_steps > wave.current_step
            ):
                elapsed = (datetime.now(timezone.utc) - wave.started_at).total_seconds()
                avg_per_step = elapsed / wave.current_step
                remaining_steps = wave.total_steps - wave.current_step
                estimated_remaining = max(0, int(avg_per_step * remaining_steps))

            execution = ExecutionStatus(
                wave_id=wave.id,
                current_step=wave.current_step,
                total_steps=wave.total_steps,
                step_labels=wave.step_labels or [],
                cost_usd=float(wave.cost_usd),
                started_at=wave.started_at,
                estimated_remaining_seconds=estimated_remaining,
            )

    return ArtifactStatusResponse(
        status=artifact.status,
        execution=execution,
    )


# ---------------------------------------------------------------------------
# GET /api/artifacts/{id}/versions
# ---------------------------------------------------------------------------


@router.get("/artifacts/{artifact_id}/versions")
async def list_versions(
    artifact_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_artifact_or_404(artifact_id, db)

    result = await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .order_by(ArtifactVersion.version_number.desc())
    )
    versions = result.scalars().all()

    return {
        "items": [
            VersionItem(
                id=v.id,
                version_number=v.version_number,
                file_manifest=v.file_manifest or [],
                token_cost_usd=float(v.token_cost_usd),
                input_tokens=v.input_tokens,
                output_tokens=v.output_tokens,
                assumptions=v.assumptions or [],
                sources=v.sources or [],
                created_at=v.created_at,
            ).model_dump()
            for v in versions
        ]
    }


# ---------------------------------------------------------------------------
# GET /api/artifacts/{id}/versions/{v}/files/{path:path} — S3 proxy (AD-15)
# ---------------------------------------------------------------------------


@router.get("/artifacts/{artifact_id}/versions/{version_number}/files/{file_path:path}")
async def proxy_file(
    artifact_id: str,
    version_number: int,
    file_path: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream a file from S3 to the client.

    AD-15: Backend proxy, not pre-signed URLs. Detects content-type from extension.
    """
    await _get_artifact_or_404(artifact_id, db)

    # Verify version exists and file is in manifest
    result = await db.execute(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version_number == version_number,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise not_found("version", str(version_number))

    manifest = version.file_manifest or []
    if file_path not in manifest:
        raise not_found("file", file_path)

    # Fetch from S3 and stream
    from app.core.s3_workspace import download_artifact_file

    try:
        content = download_artifact_file(artifact_id, version_number, file_path)
    except Exception:
        raise not_found("file", file_path)

    # Detect content type
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = "application/octet-stream"

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{file_path.split("/")[-1]}"',
        },
    )


# ---------------------------------------------------------------------------
# POST /api/artifacts/{id}/iterate
# ---------------------------------------------------------------------------


@router.post("/artifacts/{artifact_id}/iterate", status_code=202, response_model=IterateResponse)
async def iterate_artifact(
    artifact_id: str,
    body: IterateRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> IterateResponse:
    artifact = await _get_artifact_or_404(artifact_id, db)

    if artifact.status != "in_review":
        raise validation_error("Artifact must be in 'in_review' status to iterate.")

    # Check budget
    workspace = await db.get(Workspace, workspace_id)
    if workspace and float(workspace.monthly_spend_usd) >= float(workspace.monthly_budget_usd):
        raise budget_exceeded("Monthly budget ceiling reached.")

    # Get current version
    result = await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .order_by(ArtifactVersion.version_number.desc())
        .limit(1)
    )
    current_version = result.scalar_one_or_none()

    # Create contextual comment
    comment = ContextualComment(
        id=str(uuid.uuid4()),
        artifact_version_id=current_version.id if current_version else artifact_id,
        file_path=body.file_path,
        highlighted_text=body.highlighted_text,
        highlight_start=body.highlight_start,
        highlight_end=body.highlight_end,
        instruction=body.instruction,
    )
    db.add(comment)

    # Route the brief for iteration
    agent_result = await db.execute(
        select(Agent)
        .where(Agent.workspace_id == workspace_id)
        .where(Agent.archived_at.is_(None))
    )
    roster_agents = agent_result.scalars().all()

    from app.agents.router import route_brief
    routing_result = await route_brief(artifact, roster_agents)

    # Create execution wave
    wave = ExecutionWave(
        id=str(uuid.uuid4()),
        artifact_id=artifact_id,
        trigger="iteration",
        trigger_comment_id=comment.id,
        dag_plan=routing_result.dag_plan,
        assembled_team=[t for t in routing_result.assembled_team],
        status="queued",
        total_steps=len(routing_result.step_labels),
        step_labels=routing_result.step_labels,
    )
    db.add(wave)

    artifact.status = "drafting"
    await db.flush()

    from app.core.celery_app import execute_artifact_dag
    execute_artifact_dag.delay(wave.id)

    return IterateResponse(
        comment_id=comment.id,
        execution_wave_id=wave.id,
        artifact_status="drafting",
        message="Iteration started.",
    )


# ---------------------------------------------------------------------------
# PATCH /api/artifacts/{id}/approve
# ---------------------------------------------------------------------------


@router.patch("/artifacts/{artifact_id}/approve", response_model=ApproveResponse)
async def approve_artifact(
    artifact_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ApproveResponse:
    artifact = await _get_artifact_or_404(artifact_id, db)

    if artifact.status != "in_review":
        raise validation_error("Artifact must be in 'in_review' status to approve.")

    artifact.status = "approved"
    artifact.approved_at = datetime.now(timezone.utc)
    await db.flush()

    # Check reflection trigger for all agents involved
    from app.agents.reflection import should_trigger_reflection

    for wave_result in await db.execute(
        select(ExecutionWave).where(ExecutionWave.artifact_id == artifact_id)
    ):
        wave = wave_result[0]
        for team_member in (wave.assembled_team or []):
            agent_id = team_member.get("agent_id")
            if agent_id:
                should_reflect = await should_trigger_reflection(agent_id, db)
                if should_reflect:
                    from app.core.celery_app import execute_agent_reflection
                    execute_agent_reflection.delay(agent_id)

    return ApproveResponse(
        id=artifact.id,
        status=artifact.status,
        approved_at=artifact.approved_at,
    )


# ---------------------------------------------------------------------------
# PATCH /api/artifacts/{id}/cancel
# ---------------------------------------------------------------------------


@router.patch("/artifacts/{artifact_id}/cancel", response_model=CancelResponse)
async def cancel_artifact(
    artifact_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> CancelResponse:
    artifact = await _get_artifact_or_404(artifact_id, db)

    if artifact.status in ("approved", "cancelled"):
        raise validation_error(
            f"Cannot cancel artifact in '{artifact.status}' status."
        )

    # If drafting, revoke active Celery task
    if artifact.status == "drafting":
        result = await db.execute(
            select(ExecutionWave)
            .where(ExecutionWave.artifact_id == artifact_id)
            .where(ExecutionWave.status.in_(["queued", "running"]))
        )
        active_waves = result.scalars().all()
        for wave in active_waves:
            wave.status = "cancelled"
            if wave.celery_task_id:
                try:
                    from app.core.celery_app import celery_app
                    celery_app.control.revoke(wave.celery_task_id, terminate=True)
                except Exception:
                    logger.warning("Failed to revoke Celery task %s", wave.celery_task_id)

    artifact.status = "cancelled"
    artifact.cancelled_at = datetime.now(timezone.utc)
    await db.flush()

    return CancelResponse(
        id=artifact.id,
        status=artifact.status,
        cancelled_at=artifact.cancelled_at,
    )


# ---------------------------------------------------------------------------
# POST /api/artifacts/{id}/retry — re-queue a failed execution
# ---------------------------------------------------------------------------


@router.post("/artifacts/{artifact_id}/retry", status_code=202, response_model=RetryResponse)
async def retry_artifact(
    artifact_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> RetryResponse:
    """Re-queue execution for an artifact whose last wave failed.

    Creates a new ExecutionWave (trigger=retry) from the failed wave's dag_plan.
    Only valid when artifact.status == 'drafting' and a failed wave exists.
    """
    artifact = await _get_artifact_or_404(artifact_id, db)

    if artifact.status != "drafting":
        raise validation_error(
            f"Cannot retry artifact in '{artifact.status}' status. "
            "Only 'drafting' artifacts with a failed execution can be retried."
        )

    # Check monthly budget
    workspace = await db.get(Workspace, workspace_id)
    if workspace and float(workspace.monthly_spend_usd) >= float(workspace.monthly_budget_usd):
        raise budget_exceeded("Monthly budget ceiling reached.")

    # Find the most recent failed wave to copy the dag_plan from
    result = await db.execute(
        select(ExecutionWave)
        .where(ExecutionWave.artifact_id == artifact_id)
        .where(ExecutionWave.status == "failed")
        .order_by(ExecutionWave.created_at.desc())
        .limit(1)
    )
    failed_wave = result.scalar_one_or_none()
    if failed_wave is None:
        raise validation_error("No failed execution wave found for this artifact.")

    wave = ExecutionWave(
        id=str(uuid.uuid4()),
        artifact_id=artifact_id,
        trigger="retry",
        dag_plan=failed_wave.dag_plan,
        assembled_team=failed_wave.assembled_team,
        status="queued",
        total_steps=failed_wave.total_steps,
        step_labels=failed_wave.step_labels,
    )
    db.add(wave)
    await db.flush()

    from app.core.celery_app import execute_artifact_dag
    execute_artifact_dag.delay(wave.id)

    return RetryResponse(
        artifact_id=artifact.id,
        execution_wave_id=wave.id,
        status="drafting",
    )


# ---------------------------------------------------------------------------
# GET /api/projects/{pid}/artifacts — list artifacts by project
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/artifacts", response_model=PaginatedResponse[ArtifactListItem])
async def list_project_artifacts(
    project_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=100),
    cursor: str | None = Query(None),
    status: str | None = Query(None),
) -> PaginatedResponse[ArtifactListItem]:
    # Verify project
    project = await db.get(Project, project_id)
    if project is None or project.workspace_id != workspace_id:
        raise not_found("project", project_id)

    query = select(Artifact).where(Artifact.project_id == project_id)
    if status:
        query = query.where(Artifact.status == status)

    query = apply_cursor_pagination(
        query, cursor=cursor, limit=limit,
        sort_columns=[Artifact.created_at, Artifact.id],
    )

    result = await db.execute(query)
    rows = list(result.scalars().all())
    paged = paginate(rows, limit=limit, sort_keys=["created_at", "id"])

    return PaginatedResponse[ArtifactListItem](
        items=[
            ArtifactListItem(
                id=a.id,
                project_id=a.project_id,
                artifact_type=a.artifact_type,
                title=a.title,
                status=a.status,
                total_cost_usd=float(a.total_cost_usd),
                current_version=a.current_version,
                git_feature_branch=a.git_feature_branch,
                git_pr_url=a.git_pr_url,
                git_pr_number=a.git_pr_number,
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
            for a in paged.items
        ],
        next_cursor=paged.next_cursor,
        has_more=paged.has_more,
    )


# ---------------------------------------------------------------------------
# POST /api/briefs/sufficiency-check — standalone validation
# ---------------------------------------------------------------------------


@router.post("/briefs/sufficiency-check", response_model=SufficiencyResponse)
async def standalone_sufficiency_check(
    body: StandaloneSufficiencyRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> SufficiencyResponse:
    """Standalone sufficiency check — no artifact required."""
    workspace = await db.get(Workspace, workspace_id)

    # Create a mock artifact-like object for the sufficiency engine
    from types import SimpleNamespace
    mock_artifact = SimpleNamespace(
        title=body.title,
        goal=body.goal,
        target_audience=body.target_audience,
        context=body.context,
        description=body.description,
        artifact_type=body.artifact_type,
        git_repo_url=None,
    )

    from app.agents.sufficiency import run_sufficiency_check
    result = await run_sufficiency_check(mock_artifact, workspace)

    return SufficiencyResponse(
        eligible=result.eligible,
        score=result.score,
        issues=[
            SufficiencyIssueSchema(
                severity=i.severity,
                field=i.field,
                matched_text=i.matched_text,
                issue=i.issue,
                suggestion=i.suggestion,
            )
            for i in result.issues
        ],
    )
