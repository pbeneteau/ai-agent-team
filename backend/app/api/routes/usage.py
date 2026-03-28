"""Usage & cost tracking endpoints.

Ref: TDD-04 Section 12.
Aggregates stats from execution_waves, artifact_versions, and workspace budget.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.usage import (
    ArtifactUsage,
    BudgetInfo,
    DailyBreakdown,
    ModelUsage,
    UpdateBudgetRequest,
    UpdateBudgetResponse,
    UsageResponse,
)
from app.core.database import get_db
from app.core.workspace_id import get_workspace_id
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.execution_wave import ExecutionWave
from app.models.project import Project
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/usage", tags=["usage"])


# ---------------------------------------------------------------------------
# GET /api/usage — aggregate stats
# ---------------------------------------------------------------------------


@router.get("")
async def get_usage(
    period: str = Query("month", pattern="^(day|week|month)$"),
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> UsageResponse:
    now = datetime.now(timezone.utc)

    # Determine period start
    if period == "day":
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        days_since_monday = now.weekday()
        period_start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:  # month
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Get project IDs for this workspace
    project_ids_q = select(Project.id).where(Project.workspace_id == workspace_id)

    # Get artifact IDs for this workspace
    artifact_ids_q = (
        select(Artifact.id)
        .where(Artifact.project_id.in_(project_ids_q))
    )

    # Aggregate from execution_waves within the period
    waves_q = (
        select(
            func.coalesce(func.sum(ExecutionWave.cost_usd), 0).label("total_cost"),
            func.coalesce(func.sum(ExecutionWave.input_tokens), 0).label("total_input"),
            func.coalesce(func.sum(ExecutionWave.output_tokens), 0).label("total_output"),
        )
        .where(
            ExecutionWave.artifact_id.in_(artifact_ids_q),
            ExecutionWave.created_at >= period_start,
        )
    )
    wave_result = await db.execute(waves_q)
    wave_row = wave_result.one()
    total_cost = float(wave_row.total_cost)
    total_input = int(wave_row.total_input)
    total_output = int(wave_row.total_output)

    # Get workspace budget info
    workspace = await db.get(Workspace, workspace_id)
    monthly_limit = float(workspace.monthly_budget_usd) if workspace else 50.0
    monthly_spent = float(workspace.monthly_spend_usd) if workspace else 0.0
    remaining = max(0, monthly_limit - monthly_spent)
    usage_pct = int((monthly_spent / monthly_limit * 100) if monthly_limit > 0 else 0)

    budget = BudgetInfo(
        monthly_limit_usd=monthly_limit,
        monthly_spent_usd=monthly_spent,
        remaining_usd=remaining,
        usage_pct=usage_pct,
    )

    # By-model breakdown — estimate from token ratios using pricing
    # Since we don't store model per wave, approximate from assembled_team
    by_model: dict[str, ModelUsage] = {}
    if total_cost > 0:
        by_model["sonnet"] = ModelUsage(
            cost_usd=round(total_cost, 2),
            input_tokens=total_input,
            output_tokens=total_output,
        )

    # By-artifact breakdown
    artifact_q = (
        select(
            Artifact.id,
            Artifact.title,
            func.coalesce(func.sum(ExecutionWave.cost_usd), 0).label("cost"),
            func.count(ArtifactVersion.id.distinct()).label("versions"),
        )
        .join(ExecutionWave, ExecutionWave.artifact_id == Artifact.id, isouter=True)
        .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id, isouter=True)
        .where(
            Artifact.project_id.in_(project_ids_q),
            ExecutionWave.created_at >= period_start,
        )
        .group_by(Artifact.id, Artifact.title)
        .order_by(func.sum(ExecutionWave.cost_usd).desc())
        .limit(20)
    )
    artifact_result = await db.execute(artifact_q)
    by_artifact = [
        ArtifactUsage(
            artifact_id=row.id,
            title=row.title,
            cost_usd=round(float(row.cost), 2),
            versions=int(row.versions),
        )
        for row in artifact_result.all()
    ]

    # Daily breakdown
    daily_q = (
        select(
            cast(func.date(ExecutionWave.created_at), String).label("date"),
            func.coalesce(func.sum(ExecutionWave.cost_usd), 0).label("cost"),
            func.count(ExecutionWave.artifact_id.distinct()).label("artifact_count"),
        )
        .where(
            ExecutionWave.artifact_id.in_(artifact_ids_q),
            ExecutionWave.created_at >= period_start,
        )
        .group_by(func.date(ExecutionWave.created_at))
        .order_by(func.date(ExecutionWave.created_at).desc())
    )
    daily_result = await db.execute(daily_q)
    daily_breakdown = [
        DailyBreakdown(
            date=str(row.date),
            cost_usd=round(float(row.cost), 2),
            artifact_count=int(row.artifact_count),
        )
        for row in daily_result.all()
    ]

    return UsageResponse(
        period=period,
        period_start=period_start.isoformat(),
        total_cost_usd=round(total_cost, 2),
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        budget=budget,
        by_model=by_model,
        by_artifact=by_artifact,
        daily_breakdown=daily_breakdown,
    )


# ---------------------------------------------------------------------------
# PATCH /api/usage/budget — update monthly budget ceiling
# ---------------------------------------------------------------------------


@router.patch("/budget")
async def update_budget(
    body: UpdateBudgetRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> UpdateBudgetResponse:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        from app.core.errors import not_found
        raise not_found("workspace", workspace_id)

    workspace.monthly_budget_usd = body.monthly_budget_usd
    await db.flush()

    monthly_spent = float(workspace.monthly_spend_usd)
    remaining = max(0, body.monthly_budget_usd - monthly_spent)

    return UpdateBudgetResponse(
        monthly_budget_usd=body.monthly_budget_usd,
        monthly_spent_usd=monthly_spent,
        remaining_usd=remaining,
    )
