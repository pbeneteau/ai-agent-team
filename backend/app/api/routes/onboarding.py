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
    {"name": "Product Expert", "specialization": "Product strategy, user flows, and requirements analysis"},
    {"name": "Design Expert", "specialization": "UI/UX design, component architecture, and design systems"},
    {"name": "Frontend Dev", "specialization": "Frontend implementation, responsive UI, and accessibility"},
    {"name": "Backend Dev", "specialization": "Backend architecture, APIs, databases, and infrastructure"},
    {"name": "Content Writer", "specialization": "Technical writing, documentation, and content strategy"},
    {"name": "QA Engineer", "specialization": "Quality assurance, test planning, and bug analysis"},
    {"name": "Research Analyst", "specialization": "Market research, competitive analysis, and data gathering"},
]

ROSTER_BY_USE_CASE: dict[str, list[int]] = {
    "code": [0, 1, 2, 3, 5],  # product, design, frontend, backend, QA
    "content": [0, 4, 6],  # product, writer, researcher
    "both": [0, 1, 2, 3, 4, 5, 6],  # all
}


# ---------------------------------------------------------------------------
# Roster generation via Haiku (with fallback)
# ---------------------------------------------------------------------------


async def _generate_roster(
    company_name: str,
    domain_description: str,
    tech_stack: str | None,
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
            "You generate AI agent rosters for companies. Output a JSON array of objects "
            "with 'name' and 'specialization' keys. Each agent should be specialized for "
            "the company's domain and tech stack. Return 5-7 agents. Output valid JSON only."
        )
        user_msg = (
            f"Company: {company_name}\n"
            f"Domain: {domain_description}\n"
            f"Tech Stack: {tech_stack or 'Not specified'}\n"
            f"Use Case: {use_case}\n\n"
            f"Generate a team of AI agents for this company."
        )
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
            tech_stack=body.tech_stack,
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
    workspace.tech_stack = body.tech_stack

    # Generate roster
    roster_specs = await _generate_roster(
        body.company_name,
        body.domain_description,
        body.tech_stack,
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
                status=a.status,
                readiness_score=a.readiness_score,
                progression_level=a.progression_level,
            )
            for a in agents
        ],
    )
