"""Knowledge readiness scoring — heuristic formula for agent preparedness.

Ref: TDD-03 Section 10 (knowledge readiness scoring).
     TDD-03 Section 10.1 (heuristic formula: 4 components, max 100).
     TDD-03 Section 10.2 (threshold mapping for auto-assembly eligibility).

Synchronous DB calculation, no LLM call (AD-12).
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.agent_skill import AgentSkill

logger = logging.getLogger(__name__)


async def compute_readiness_score(
    agent_id: str,
    project_id: str | None,
    db_session: AsyncSession,
) -> int:
    """Compute agent readiness score (0-100).

    Ref: TDD-03 Section 10.1.

    Components:
    - has_skills (40 points): agent has at least 1 skill entry
    - has_briefing (30 points): agent has ingested the current project brief
    - onboarding_complete (20 points): agent has moved past 'learning' status
    - has_learnings (10 points): agent has at least 1 work_learning entry

    If no project_id is provided, briefing gets full credit (no project context needed).
    """
    score = 0

    # 40 points: has at least 1 skill entry
    skill_count = await db_session.scalar(
        select(func.count()).select_from(AgentSkill).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.category == "skill",
        )
    )
    if skill_count and skill_count > 0:
        score += 40

    # 30 points: has briefing for current project (or no project = full credit)
    if project_id:
        briefing_count = await db_session.scalar(
            select(func.count()).select_from(AgentSkill).where(
                AgentSkill.agent_id == agent_id,
                AgentSkill.category == "briefing",
            )
        )
        if briefing_count and briefing_count > 0:
            score += 30
    else:
        score += 30  # No project context needed = full credit

    # 20 points: onboarding complete (agent has moved past 'learning' at least once)
    agent = await db_session.get(Agent, agent_id)
    if agent is not None and (agent.completed_artifacts > 0 or agent.status != "learning"):
        score += 20

    # 10 points: has at least 1 work_learning entry
    learning_count = await db_session.scalar(
        select(func.count()).select_from(AgentSkill).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.category == "work_learning",
        )
    )
    if learning_count and learning_count > 0:
        score += 10

    return score


async def update_agent_readiness(
    agent_id: str,
    db_session: AsyncSession,
    project_id: str | None = None,
) -> int:
    """Compute readiness score and write it to the agent row.

    Returns the computed score.
    """
    score = await compute_readiness_score(agent_id, project_id, db_session)

    agent = await db_session.get(Agent, agent_id)
    if agent is not None:
        agent.readiness_score = score
        await db_session.flush()
        logger.info(
            "Updated readiness score for agent %s: %d",
            agent_id,
            score,
        )

    return score
