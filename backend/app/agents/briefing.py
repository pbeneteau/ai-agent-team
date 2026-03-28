"""Project briefing — distributes project context to all roster agents.

Ref: TDD-03 Section 11.3 (project briefing).

When a project brief is published (or updated), all active roster agents
receive a briefing entry in agent_skills. Re-publishing replaces (not stacks)
existing briefing entries for that project.

Briefing entries are NOT counted against the 8k memory budget — they are
injected at position 7 of the user message (Section C: Current Task).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.memory import count_tokens
from app.agents.readiness import update_agent_readiness
from app.models.agent import Agent
from app.models.agent_skill import AgentSkill
from app.models.project import Project

logger = logging.getLogger(__name__)


async def brief_all_agents(
    project: Project,
    db_session: AsyncSession,
) -> int:
    """Brief all active (non-archived) agents on a project.

    Ref: TDD-03 Section 11.3.

    For each active agent:
    1. Delete existing briefing entry for this project
    2. Insert new briefing entry with the published brief content
    3. Recompute readiness score

    Returns the number of agents briefed.
    """
    if not project.brief_published:
        logger.warning(
            "brief_all_agents called for project %s but brief_published is empty",
            project.id,
        )
        return 0

    # Get all active (non-archived) agents in the workspace
    result = await db_session.execute(
        select(Agent).where(
            Agent.workspace_id == project.workspace_id,
            Agent.archived_at.is_(None),
        )
    )
    agents = result.scalars().all()

    briefed_count = 0
    for agent in agents:
        await brief_agent(agent, project, db_session)
        briefed_count += 1

    logger.info(
        "Briefed %d agents on project %s (%s)",
        briefed_count,
        project.id,
        project.name,
    )

    return briefed_count


async def brief_agent(
    agent: Agent,
    project: Project,
    db_session: AsyncSession,
) -> None:
    """Brief a single agent on a project.

    1. Delete existing briefing for this project (replace, not stack)
    2. Insert new briefing entry
    3. Recompute readiness score
    """
    briefing_title = f"Project: {project.name}"

    # Delete existing briefing for this project
    await db_session.execute(
        delete(AgentSkill).where(
            AgentSkill.agent_id == agent.id,
            AgentSkill.category == "briefing",
            AgentSkill.title == briefing_title,
        )
    )

    # Insert new briefing entry
    briefing = AgentSkill(
        id=str(uuid.uuid4()),
        agent_id=agent.id,
        category="briefing",
        title=briefing_title,
        content=project.brief_published or "",
        token_count=count_tokens(project.brief_published or ""),
    )
    db_session.add(briefing)
    await db_session.flush()

    # Recompute readiness score with project context
    await update_agent_readiness(agent.id, db_session, project_id=project.id)
