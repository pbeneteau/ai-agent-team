"""Onboarding endpoint — first-time workspace setup.

Ref: TDD-04 Section 2.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.onboarding import (
    AgentSummary,
    OnboardingRequest,
    OnboardingResponse,
    WorkspaceSummary,
)
from app.core.database import get_db
from app.core.errors import conflict
from app.core.workspace_id import get_workspace_id
from app.models.agent import Agent
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["onboarding"])

# ---------------------------------------------------------------------------
# Default roster fallback (when Haiku LLM call fails)
# ---------------------------------------------------------------------------

DEFAULT_ROSTER: list[dict[str, str]] = [
    # Leads (always present for code workspaces)
    {"name": "Tech Lead", "specialization": "Technical architecture, code quality standards, and engineering delegation", "role": "lead"},
    {"name": "PM Lead", "specialization": "Product requirements, user stories, scope definition, and cross-team coordination", "role": "lead"},
    {"name": "Design Lead", "specialization": "UI/UX design direction, design systems, and component specification", "role": "lead"},
    # Workers
    {"name": "Frontend Dev", "specialization": "Frontend implementation, responsive UI, accessibility, and component building", "role": "worker"},
    {"name": "Backend Dev", "specialization": "Backend architecture, REST APIs, databases, and server-side logic", "role": "worker"},
    {"name": "QA Engineer", "specialization": "Quality assurance, automated testing, and bug analysis", "role": "worker"},
]

ROSTER_BY_USE_CASE: dict[str, list[int]] = {
    "code": [0, 1, 2, 3, 4, 5],  # tech lead, PM lead, design lead, frontend, backend, QA
    "content": [1, 3],            # PM lead, frontend dev (writer proxy)
    "both": [0, 1, 2, 3, 4, 5],  # all
}


# ---------------------------------------------------------------------------
# Roster generation via Haiku (with fallback)
# ---------------------------------------------------------------------------


async def _generate_roster(
    company_name: str,
    domain_description: str,
    product_description: str | None,
    tech_stack: str | None,
    company_stage: str | None,
    target_audience: str | None,
    main_goals: str | None,
    existing_team: str | None,
    use_case: str,
) -> list[dict[str, str]]:
    """Generate a roster via Haiku LLM call, with hardcoded fallback."""
    import json

    from app.agents.anthropic_runner import get_anthropic_client
    from app.config.settings import settings

    indices = ROSTER_BY_USE_CASE.get(use_case, ROSTER_BY_USE_CASE["both"])
    fallback = [DEFAULT_ROSTER[i] for i in indices]

    try:
        client = get_anthropic_client()
        system_prompt = (
            "You generate AI agent rosters for software teams. Output a JSON array of objects "
            "with 'name', 'specialization', and 'role' keys. "
            "The 'role' field must be either 'lead' or 'worker'.\n\n"
            "LEADS plan, delegate work to specialists, and review outputs. They are strategic.\n"
            "WORKERS are specialist implementers who execute tasks assigned by leads.\n\n"
            "Rules:\n"
            "- Always include a Tech Lead (lead) and PM Lead (lead) for code workspaces.\n"
            "- Include a Design Lead (lead) if the product has significant UI/UX work.\n"
            "- Include contextual leads only if clearly relevant: Security Lead, DevOps Lead, "
            "Data Lead, or Mobile Lead.\n"
            "- Workers: Frontend Dev, Backend Dev, QA Engineer, Mobile Dev, Data Engineer, "
            "DevOps Engineer — pick those that fit the tech stack.\n"
            "- Total agents: 6-10 (2-4 leads + 4-6 workers).\n"
            "- Specialize names and descriptions for the company's domain.\n"
            "Output valid JSON only — no explanation, no markdown."
        )
        context_lines = [
            f"Company: {company_name}",
            f"Domain / Industry: {domain_description}",
        ]
        if product_description:
            context_lines.append(f"Product: {product_description}")
        if company_stage:
            context_lines.append(f"Stage: {company_stage}")
        if target_audience:
            context_lines.append(f"Target Audience: {target_audience}")
        if main_goals:
            context_lines.append(f"Main Goals: {main_goals}")
        if existing_team:
            context_lines.append(f"Existing Team Roles: {existing_team}")
        if tech_stack:
            context_lines.append(f"Tech Stack: {tech_stack}")
        context_lines.append(f"Use Case: {use_case}")
        context_lines.append(
            "\nGenerate a tailored team of leads and workers for this company. "
            "Specialize each agent's name and description for the domain."
        )
        user_msg = "\n".join(context_lines)

        response = await client.messages.create(
            model=settings.MODEL_HAIKU,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        roster = json.loads(response.content[0].text)
        if isinstance(roster, list) and all(
            isinstance(r, dict) and "name" in r and "specialization" in r
            for r in roster
        ):
            # Normalize role field — default to worker if missing or invalid
            for agent in roster:
                if agent.get("role") not in ("lead", "worker"):
                    agent["role"] = "worker"
            return roster
    except Exception:
        logger.warning("Haiku roster generation failed, using fallback")

    return fallback


# ---------------------------------------------------------------------------
# POST /api/onboarding
# ---------------------------------------------------------------------------


@router.post("/onboarding", status_code=201, response_model=OnboardingResponse)
async def onboard(
    body: OnboardingRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> OnboardingResponse:
    """First-time workspace setup. Generates default roster and starts agent learning."""
    # Load workspace
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        # Create workspace if it doesn't exist (first run)
        workspace = Workspace(
            id=workspace_id,
            name=body.company_name,
            domain_description=body.domain_description,
            product_description=body.product_description,
            tech_stack=body.tech_stack,
            company_stage=body.company_stage,
            target_audience=body.target_audience,
            main_goals=body.main_goals,
            existing_team=body.existing_team,
        )
        db.add(workspace)
        await db.flush()

    # 409 if already onboarded
    if workspace.onboarding_completed:
        raise conflict(
            "ALREADY_ONBOARDED",
            "Workspace has already completed onboarding.",
        )

    # Update workspace with onboarding info
    workspace.name = body.company_name
    workspace.domain_description = body.domain_description
    workspace.product_description = body.product_description
    workspace.tech_stack = body.tech_stack
    workspace.company_stage = body.company_stage
    workspace.target_audience = body.target_audience
    workspace.main_goals = body.main_goals
    workspace.existing_team = body.existing_team

    # Generate roster
    roster_specs = await _generate_roster(
        body.company_name,
        body.domain_description,
        body.product_description,
        body.tech_stack,
        body.company_stage,
        body.target_audience,
        body.main_goals,
        body.existing_team,
        body.use_case,
    )

    # Create agents
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    agents: list[Agent] = []
    for spec in roster_specs:
        agent = Agent(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=spec["name"],
            specialization=spec["specialization"],
            role=spec.get("role", "worker"),
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
        agents.append(agent)

    # Mark onboarding complete
    workspace.onboarding_completed = True
    await db.flush()

    # Enqueue learning tasks
    from app.core.celery_app import execute_agent_learning

    for agent in agents:
        execute_agent_learning.delay(agent.id)

    return OnboardingResponse(
        workspace=WorkspaceSummary(
            id=workspace.id,
            name=workspace.name,
            onboarding_completed=workspace.onboarding_completed,
        ),
        agents=[
            AgentSummary(
                id=a.id,
                name=a.name,
                specialization=a.specialization,
                role=a.role,
                status=a.status,
                readiness_score=a.readiness_score,
                progression_level=a.progression_level,
            )
            for a in agents
        ],
    )
