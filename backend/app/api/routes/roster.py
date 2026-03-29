"""Roster (agent) CRUD endpoints.

Ref: TDD-04 Section 3 (all roster endpoints).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone


from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.roster import (
    ActionResponse,
    AgentDetail,
    AgentListItem,
    ArchiveResponse,
    BudgetInfo,
    CreateAgentRequest,
    DismissResponse,
    GlobalReadiness,
    AgentAttention,
    KnowledgeRecommendation,
    LearningProfile,
    ReadinessBreakdown,
    ReadinessByLevel,
    ReadinessByStatus,
    ReadinessComponent,
    ResearchRequest,
    RestoreResponse,
    SkillItem,
    SkillsListResponse,
    SkillsSummary,
    UpdateAgentRequest,
)
from app.core.database import get_db
from app.core.errors import not_found, validation_error
from app.core.pagination import (
    PaginatedResponse,
    apply_cursor_pagination,
    paginate,
    DEFAULT_LIMIT,
)
from app.core.workspace_id import get_workspace_id
from app.models.agent import Agent
from app.models.agent_skill import AgentSkill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/roster", tags=["roster"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_agent_or_404(
    agent_id: str, workspace_id: str, db: AsyncSession
) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise not_found("agent", agent_id)
    return agent


async def _build_skills_summary(agent_id: str, db: AsyncSession) -> SkillsSummary:
    result = await db.execute(
        select(
            AgentSkill.category,
            func.count().label("cnt"),
            func.coalesce(func.sum(AgentSkill.token_count), 0).label("tokens"),
        )
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
        .group_by(AgentSkill.category)
    )
    rows = {r[0]: (r[1], int(r[2])) for r in result.all()}
    skill_count, skill_tokens = rows.get("skill", (0, 0))
    learning_count, learning_tokens = rows.get("work_learning", (0, 0))
    total = skill_tokens + learning_tokens
    return SkillsSummary(
        total_skill_tokens=skill_tokens,
        total_learning_tokens=learning_tokens,
        budget_used_pct=int(total / 8000 * 100) if total else 0,
        skill_count=skill_count,
        learning_count=learning_count,
    )


# ---------------------------------------------------------------------------
# GET /api/roster — list agents
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[AgentListItem])
async def list_agents(
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=100),
    cursor: str | None = Query(None),
    status: str | None = Query(None),
    include_archived: bool = Query(False),
) -> PaginatedResponse[AgentListItem]:
    query = select(Agent).where(Agent.workspace_id == workspace_id)

    if not include_archived:
        query = query.where(Agent.archived_at.is_(None))
    if status:
        query = query.where(Agent.status == status)

    query = apply_cursor_pagination(
        query,
        cursor=cursor,
        limit=limit,
        sort_columns=[Agent.created_at, Agent.id],
    )

    result = await db.execute(query)
    rows = list(result.scalars().all())

    paged = paginate(rows, limit=limit, sort_keys=["created_at", "id"])
    return PaginatedResponse[AgentListItem](
        items=[
            AgentListItem(
                id=a.id,
                name=a.name,
                specialization=a.specialization,
                role=a.role,
                description=a.description,
                status=a.status,
                readiness_score=a.readiness_score,
                progression_level=a.progression_level,
                model_tier=a.model_tier,
                completed_artifacts=a.completed_artifacts,
                avg_quality_score=float(a.avg_quality_score) if a.avg_quality_score else None,
                archived_at=a.archived_at,
                created_at=a.created_at,
            )
            for a in paged.items
        ],
        next_cursor=paged.next_cursor,
        has_more=paged.has_more,
    )


# ---------------------------------------------------------------------------
# GET /api/roster/{agent_id} — agent detail
# ---------------------------------------------------------------------------


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AgentDetail:
    agent = await _get_agent_or_404(agent_id, workspace_id, db)
    summary = await _build_skills_summary(agent_id, db)

    return AgentDetail(
        id=agent.id,
        name=agent.name,
        specialization=agent.specialization,
        role=agent.role,
        description=agent.description,
        system_prompt=agent.system_prompt,
        status=agent.status,
        readiness_score=agent.readiness_score,
        progression_level=agent.progression_level,
        model_tier=agent.model_tier,
        tools=agent.tools if isinstance(agent.tools, list) else [],
        completed_artifacts=agent.completed_artifacts,
        avg_quality_score=float(agent.avg_quality_score) if agent.avg_quality_score else None,
        last_reflection_at=agent.last_reflection_at,
        archived_at=agent.archived_at,
        skills_summary=summary,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


# ---------------------------------------------------------------------------
# POST /api/roster — create agent
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=AgentDetail)
async def create_agent(
    body: CreateAgentRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AgentDetail:
    now = datetime.now(timezone.utc)
    agent = Agent(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=body.name,
        specialization=body.specialization,
        role="worker",
        description=body.description,
        model_tier=body.model_tier,
        status="learning",
        readiness_score=0,
        progression_level="apprenti",
        completed_artifacts=0,
        tools=[],
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    await db.flush()

    from app.core.celery_app import execute_agent_learning
    execute_agent_learning.delay(agent.id)

    summary = await _build_skills_summary(agent.id, db)
    return AgentDetail(
        id=agent.id,
        name=agent.name,
        specialization=agent.specialization,
        role=agent.role,
        description=agent.description,
        system_prompt=agent.system_prompt,
        status=agent.status,
        readiness_score=agent.readiness_score,
        progression_level=agent.progression_level,
        model_tier=agent.model_tier,
        tools=agent.tools if isinstance(agent.tools, list) else [],
        completed_artifacts=agent.completed_artifacts,
        avg_quality_score=None,
        last_reflection_at=None,
        archived_at=None,
        skills_summary=summary,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


# ---------------------------------------------------------------------------
# PATCH /api/roster/{agent_id} — update agent
# ---------------------------------------------------------------------------


@router.patch("/{agent_id}", response_model=AgentDetail)
async def update_agent(
    agent_id: str,
    body: UpdateAgentRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AgentDetail:
    agent = await _get_agent_or_404(agent_id, workspace_id, db)

    if body.name is not None:
        agent.name = body.name
    if body.specialization is not None:
        agent.specialization = body.specialization
    if body.description is not None:
        agent.description = body.description
    if body.model_tier is not None:
        agent.model_tier = body.model_tier

    await db.flush()

    summary = await _build_skills_summary(agent_id, db)
    return AgentDetail(
        id=agent.id,
        name=agent.name,
        specialization=agent.specialization,
        role=agent.role,
        description=agent.description,
        system_prompt=agent.system_prompt,
        status=agent.status,
        readiness_score=agent.readiness_score,
        progression_level=agent.progression_level,
        model_tier=agent.model_tier,
        tools=agent.tools if isinstance(agent.tools, list) else [],
        completed_artifacts=agent.completed_artifacts,
        avg_quality_score=float(agent.avg_quality_score) if agent.avg_quality_score else None,
        last_reflection_at=agent.last_reflection_at,
        archived_at=agent.archived_at,
        skills_summary=summary,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


# ---------------------------------------------------------------------------
# DELETE /api/roster/{agent_id} — soft archive
# ---------------------------------------------------------------------------


@router.delete("/{agent_id}", response_model=ArchiveResponse)
async def archive_agent(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ArchiveResponse:
    agent = await _get_agent_or_404(agent_id, workspace_id, db)
    agent.archived_at = datetime.now(timezone.utc)
    await db.flush()
    return ArchiveResponse(id=agent.id, archived_at=agent.archived_at)


# ---------------------------------------------------------------------------
# POST /api/roster/{agent_id}/restore — unarchive
# ---------------------------------------------------------------------------


@router.post("/{agent_id}/restore", response_model=RestoreResponse)
async def restore_agent(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> RestoreResponse:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise not_found("agent", agent_id)
    if agent.archived_at is None:
        raise validation_error("Agent is not archived.")
    agent.archived_at = None
    await db.flush()
    return RestoreResponse(id=agent.id, restored=True)


# ---------------------------------------------------------------------------
# DELETE /api/roster/{agent_id}/permanent — hard delete
# ---------------------------------------------------------------------------


@router.delete("/{agent_id}/permanent", status_code=204)
async def permanent_delete_agent(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    agent = await _get_agent_or_404(agent_id, workspace_id, db)
    await db.delete(agent)
    await db.flush()


# ---------------------------------------------------------------------------
# GET /api/roster/{agent_id}/skills
# ---------------------------------------------------------------------------


@router.get("/{agent_id}/skills", response_model=SkillsListResponse)
async def list_skills(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
    category: str | None = Query(None),
) -> SkillsListResponse:
    await _get_agent_or_404(agent_id, workspace_id, db)

    query = select(AgentSkill).where(AgentSkill.agent_id == agent_id)
    if category:
        query = query.where(AgentSkill.category == category)
    query = query.order_by(AgentSkill.category, AgentSkill.updated_at.desc())

    result = await db.execute(query)
    skills = result.scalars().all()

    # Budget info
    budget_result = await db.execute(
        select(func.coalesce(func.sum(AgentSkill.token_count), 0))
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
    )
    used_tokens = int(budget_result.scalar_one())

    return SkillsListResponse(
        items=[
            SkillItem(
                id=s.id,
                category=s.category,
                title=s.title,
                content=s.content,
                token_count=s.token_count,
                source_artifact_id=s.source_artifact_id,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in skills
        ],
        budget=BudgetInfo(
            used_tokens=used_tokens,
            max_tokens=8000,
            used_pct=int(used_tokens / 8000 * 100) if used_tokens else 0,
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/roster/{agent_id}/learning-profile
# ---------------------------------------------------------------------------


@router.get("/{agent_id}/learning-profile", response_model=LearningProfile)
async def learning_profile(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> LearningProfile:
    agent = await _get_agent_or_404(agent_id, workspace_id, db)

    # Compute breakdown
    skill_count = await db.scalar(
        select(func.count()).select_from(AgentSkill).where(
            AgentSkill.agent_id == agent_id, AgentSkill.category == "skill"
        )
    ) or 0
    briefing_count = await db.scalar(
        select(func.count()).select_from(AgentSkill).where(
            AgentSkill.agent_id == agent_id, AgentSkill.category == "briefing"
        )
    ) or 0
    learning_count = await db.scalar(
        select(func.count()).select_from(AgentSkill).where(
            AgentSkill.agent_id == agent_id, AgentSkill.category == "work_learning"
        )
    ) or 0
    onboarding_done = agent.completed_artifacts > 0 or agent.status != "learning"

    has_skills = ReadinessComponent(points=40 if skill_count > 0 else 0, max=40, met=skill_count > 0)
    has_briefing = ReadinessComponent(points=30 if briefing_count > 0 else 0, max=30, met=briefing_count > 0)
    onboarding_complete = ReadinessComponent(points=20 if onboarding_done else 0, max=20, met=onboarding_done)
    has_learnings = ReadinessComponent(points=10 if learning_count > 0 else 0, max=10, met=learning_count > 0)

    # Token usage
    budget_result = await db.execute(
        select(func.coalesce(func.sum(AgentSkill.token_count), 0))
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
    )
    used_tokens = int(budget_result.scalar_one())

    return LearningProfile(
        agent_id=agent.id,
        readiness_score=agent.readiness_score,
        readiness_breakdown=ReadinessBreakdown(
            has_skills=has_skills,
            has_briefing=has_briefing,
            onboarding_complete=onboarding_complete,
            has_learnings=has_learnings,
        ),
        progression_level=agent.progression_level,
        completed_artifacts=agent.completed_artifacts,
        avg_quality_score=float(agent.avg_quality_score) if agent.avg_quality_score else None,
        last_reflection_at=agent.last_reflection_at,
        skill_token_usage=BudgetInfo(
            used_tokens=used_tokens,
            max_tokens=8000,
            used_pct=int(used_tokens / 8000 * 100) if used_tokens else 0,
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/roster/{agent_id}/research
# ---------------------------------------------------------------------------


@router.post("/{agent_id}/research", status_code=202, response_model=ActionResponse)
async def trigger_research(
    agent_id: str,
    body: ResearchRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ActionResponse:
    agent = await _get_agent_or_404(agent_id, workspace_id, db)
    agent.status = "learning"
    await db.flush()

    from app.core.celery_app import execute_agent_learning
    execute_agent_learning.delay(agent_id, body.topic)

    return ActionResponse(message="Research started.", agent_status="learning")


# ---------------------------------------------------------------------------
# POST /api/roster/{agent_id}/reflect
# ---------------------------------------------------------------------------


@router.post("/{agent_id}/reflect", status_code=202, response_model=ActionResponse)
async def trigger_reflect(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ActionResponse:
    agent = await _get_agent_or_404(agent_id, workspace_id, db)
    agent.status = "reflecting"
    await db.flush()

    from app.core.celery_app import execute_agent_reflection
    execute_agent_reflection.delay(agent_id)

    return ActionResponse(message="Reflection started.", agent_status="reflecting")


# ---------------------------------------------------------------------------
# POST /api/roster/{agent_id}/knowledge
# ---------------------------------------------------------------------------


@router.post("/{agent_id}/knowledge", status_code=202, response_model=ActionResponse)
async def upload_knowledge(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
) -> ActionResponse:
    agent = await _get_agent_or_404(agent_id, workspace_id, db)

    if file is None and url is None:
        raise validation_error("One of 'file' or 'url' must be provided.")

    agent.status = "learning"
    await db.flush()

    from app.core.celery_app import execute_agent_learning
    execute_agent_learning.delay(agent_id)

    return ActionResponse(message="Knowledge ingestion started.", agent_status="learning")


# ---------------------------------------------------------------------------
# GET /api/roster/{agent_id}/knowledge-recommendations
# ---------------------------------------------------------------------------


@router.get("/{agent_id}/knowledge-recommendations")
async def list_recommendations(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Identify knowledge gaps by comparing recent workspace work against agent skills.

    Uses a Haiku LLM call to detect topics that appeared in recent artifacts
    but are absent from the agent's current skill base.
    """
    import json
    import uuid as _uuid
    from datetime import datetime, timezone

    from app.agents.anthropic_runner import get_anthropic_client
    from app.config.settings import settings
    from app.models.artifact import Artifact
    from app.models.project import Project

    agent = await _get_agent_or_404(agent_id, workspace_id, db)

    # Load agent's current skill titles
    skill_result = await db.execute(
        select(AgentSkill.title, AgentSkill.category)
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
    )
    skill_titles = [f"[{r.category}] {r.title}" for r in skill_result.all()]

    # Load recent artifact titles and goals across the workspace
    artifact_result = await db.execute(
        select(Artifact.title, Artifact.goal, Artifact.artifact_type)
        .join(Project, Project.id == Artifact.project_id)
        .where(Project.workspace_id == workspace_id)
        .order_by(Artifact.created_at.desc())
        .limit(10)
    )
    recent_artifacts = artifact_result.all()

    if not recent_artifacts:
        return {"items": []}

    artifacts_text = "\n".join(
        f"- [{a.artifact_type}] {a.title}: {a.goal or ''}"
        for a in recent_artifacts
    )
    skills_text = "\n".join(skill_titles) if skill_titles else "(none)"

    prompt = (
        f"You are analyzing knowledge gaps for an AI agent.\n\n"
        f"Agent: {agent.name} ({agent.specialization})\n\n"
        f"Current knowledge (skill titles):\n{skills_text}\n\n"
        f"Recent work items in this workspace:\n{artifacts_text}\n\n"
        "Identify up to 3 specific topics that appeared in recent work but are "
        "absent from the agent's current knowledge. Only include genuinely useful gaps.\n\n"
        "Output a JSON array only:\n"
        '[{"title": "...", "reason": "...", "suggested_action": "..."}]\n'
        "If no meaningful gaps found, output: []"
    )

    try:
        client = get_anthropic_client()
        response = await client.messages.create(
            model=settings.MODEL_HAIKU,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        items_raw = json.loads(response.content[0].text)
    except Exception:
        logger.warning("Knowledge recommendations LLM call failed for agent %s", agent_id)
        return {"items": []}

    now = datetime.now(timezone.utc)
    return {
        "items": [
            KnowledgeRecommendation(
                id=str(_uuid.uuid4()),
                type="gap",
                title=item.get("title", ""),
                reason=item.get("reason", ""),
                suggested_action=item.get("suggested_action", ""),
                created_at=now,
            ).model_dump()
            for item in items_raw
            if isinstance(item, dict) and item.get("title")
        ]
    }


# ---------------------------------------------------------------------------
# POST /api/roster/{agent_id}/knowledge-recommendations/{rec_id}/apply
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_id}/knowledge-recommendations/{rec_id}/apply",
    status_code=202,
    response_model=ActionResponse,
)
async def apply_recommendation(
    agent_id: str,
    rec_id: str,
    topic: str | None = Query(None, description="Topic from the recommendation title"),
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ActionResponse:
    agent = await _get_agent_or_404(agent_id, workspace_id, db)
    agent.status = "learning"
    await db.flush()

    from app.core.celery_app import execute_agent_learning
    execute_agent_learning.delay(agent_id, topic)

    return ActionResponse(
        message="Recommendation applied. Research started.",
        agent_status="learning",
    )


# ---------------------------------------------------------------------------
# POST /api/roster/{agent_id}/knowledge-recommendations/{rec_id}/dismiss
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_id}/knowledge-recommendations/{rec_id}/dismiss",
    response_model=DismissResponse,
)
async def dismiss_recommendation(
    agent_id: str,
    rec_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DismissResponse:
    await _get_agent_or_404(agent_id, workspace_id, db)
    return DismissResponse(id=rec_id, dismissed=True)


# ---------------------------------------------------------------------------
# GET /api/roster/readiness/global
# ---------------------------------------------------------------------------


@router.get("/readiness/global", response_model=GlobalReadiness)
async def global_readiness(
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> GlobalReadiness:
    result = await db.execute(
        select(Agent)
        .where(Agent.workspace_id == workspace_id)
        .where(Agent.archived_at.is_(None))
    )
    agents = result.scalars().all()

    total = len(agents)
    sufficient = sum(1 for a in agents if a.readiness_score >= 80)
    partial = sum(1 for a in agents if 50 <= a.readiness_score < 80)
    insufficient = sum(1 for a in agents if a.readiness_score < 50)

    by_status = {"ready": 0, "learning": 0, "reflecting": 0, "working": 0}
    for a in agents:
        if a.status in by_status:
            by_status[a.status] += 1

    avg_score = int(sum(a.readiness_score for a in agents) / total) if total else 0

    attention = []
    for a in agents:
        if a.readiness_score < 50:
            issue = "No core skills — initial learning may have failed." if a.readiness_score == 0 else "Low readiness score."
            attention.append(AgentAttention(
                agent_id=a.id,
                agent_name=a.name,
                readiness_score=a.readiness_score,
                issue=issue,
            ))

    return GlobalReadiness(
        total_agents=total,
        by_readiness=ReadinessByLevel(
            sufficient=sufficient,
            partial=partial,
            insufficient=insufficient,
        ),
        by_status=ReadinessByStatus(**by_status),
        avg_readiness_score=avg_score,
        agents_needing_attention=attention,
    )
