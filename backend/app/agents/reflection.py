"""Reflection engine — post-execution self-improvement for agents.

Ref: TDD-03 Section 9 (reflection & learning engine).
     TDD-03 Section 9.1 (trigger conditions).
     TDD-03 Section 9.2 (reflection prompt).
     TDD-03 Section 9.3 (response schema).
     TDD-03 Section 9.4 (post-reflection processing).
     TDD-03 Section 9.5 (sequential locking).
     TDD-02 Section 6 (reflection locking — FOR UPDATE row lock).

Reflection analyzes an agent's recent work and extracts reusable insights.
Triggers after artifact approval if ≥3 artifacts since last reflection
or ≥7 days since last_reflection_at.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.anthropic_runner import get_anthropic_client
from app.agents.memory import check_memory_budget, count_tokens, trigger_compaction
from app.agents.readiness import update_agent_readiness
from app.config.settings import settings
from app.models.agent import Agent
from app.models.agent_skill import AgentSkill
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.contextual_comment import ContextualComment
from app.models.execution_wave import ExecutionWave

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reflection prompt (TDD-03 Section 9.2 — verbatim)
# ---------------------------------------------------------------------------

REFLECTION_SYSTEM_PROMPT: str = """\
You are a Learning Extractor. Your job is to analyze an AI agent's recent work \
and extract reusable insights that will improve future performance.

Rules:
- Extract SPECIFIC, actionable learnings — not generic platitudes.
- Good: "User prefers bullet-point recommendations over paragraph prose"
- Bad: "Write clearly and concisely"
- Focus on: user corrections, preferences revealed through feedback, domain \
knowledge gained, effective approaches, mistakes to avoid.
- Each learning should be 1-2 sentences maximum.
- Output valid JSON only."""

REFLECTION_USER_MSG_TEMPLATE: str = """\
## Agent: {agent_name} ({specialization})

## Artifacts Completed Since Last Reflection

{artifacts_section}

## Current Skills (for deduplication — do not repeat what's already known)
{current_skills}

Extract new learnings from these artifacts. Only include insights that are NOT \
already captured in the current skills."""

# ---------------------------------------------------------------------------
# Pydantic models (TDD-03 Section 9.3)
# ---------------------------------------------------------------------------


class ReflectionInsight(BaseModel):
    """A new insight extracted from recent work."""

    title: str
    content: str
    source_artifact: str | None = None


class ReflectionCaution(BaseModel):
    """A caution/warning extracted from recent work."""

    title: str
    content: str
    source_artifact: str | None = None


class ObsoleteSkill(BaseModel):
    """A skill identified as obsolete by the reflection."""

    skill_id: str
    reason: str


class ReflectionResponse(BaseModel):
    """Full response schema from the reflection LLM call."""

    insights: list[ReflectionInsight] = []
    cautions: list[ReflectionCaution] = []
    obsolete_skills: list[ObsoleteSkill] = []


# ---------------------------------------------------------------------------
# Trigger check (TDD-03 Section 9.1)
# ---------------------------------------------------------------------------


async def should_trigger_reflection(
    agent_id: str,
    db_session: AsyncSession,
) -> bool:
    """Check if reflection should trigger for this agent.

    Returns True if:
    - Agent has completed ≥ 3 artifacts since last reflection, OR
    - It has been ≥ 7 days since agent.last_reflection_at

    Checked in application code after the approval state transition.
    """
    agent = await db_session.get(Agent, agent_id)
    if agent is None:
        return False

    # Count artifacts completed since last reflection
    artifacts_since = await _count_artifacts_since_last_reflection(
        agent_id, agent.last_reflection_at, db_session
    )
    if artifacts_since >= 3:
        return True

    # Check time since last reflection
    if agent.last_reflection_at is None:
        # Never reflected — only trigger if there are artifacts to reflect on
        return artifacts_since > 0

    days_since = (datetime.now(timezone.utc) - agent.last_reflection_at).days
    if days_since >= 7:
        return True

    return False


async def _count_artifacts_since_last_reflection(
    agent_id: str,
    last_reflection_at: datetime | None,
    db_session: AsyncSession,
) -> int:
    """Count artifacts completed by this agent since the last reflection.

    An artifact is "completed by this agent" if there's an execution_wave
    with this agent in its assembled_team that produced a version for an
    approved artifact.
    """
    # Find execution waves where this agent participated
    query = (
        select(func.count(func.distinct(Artifact.id)))
        .select_from(Artifact)
        .join(ExecutionWave, ExecutionWave.artifact_id == Artifact.id)
        .where(Artifact.status == "approved")
    )

    if last_reflection_at is not None:
        query = query.where(Artifact.approved_at > last_reflection_at)

    result = await db_session.scalar(query)
    return result or 0


# ---------------------------------------------------------------------------
# Core entry point
# ---------------------------------------------------------------------------


async def execute_reflection(agent_id: str) -> None:
    """Run the full reflection lifecycle for an agent.

    Ref: TDD-03 Section 9, TDD-02 Section 6.

    Lifecycle:
    1. Acquire FOR UPDATE lock on agent row
    2. Set agent.status = 'reflecting'
    3. Load recent artifacts and their contextual comments
    4. Build reflection prompt
    5. Call Sonnet, parse JSON response
    6. Post-processing: insert new skills/learnings, remove obsolete entries,
       check token budget, trigger compaction if needed
    7. Set agent.status = 'ready', update last_reflection_at
    """
    from app.core.database import async_session_maker

    async with async_session_maker() as db_session:
        try:
            await _execute_reflection_impl(agent_id, db_session)
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            # Ensure agent is not stuck in 'reflecting'
            try:
                await _recover_agent_status(agent_id, db_session)
                await db_session.commit()
            except Exception:
                logger.exception(
                    "Failed to recover agent %s status after reflection failure",
                    agent_id,
                )
            raise


async def _execute_reflection_impl(
    agent_id: str,
    db_session: AsyncSession,
) -> None:
    """Internal reflection implementation with row locking."""
    # 1. Acquire FOR UPDATE lock on agent row (TDD-02 Section 6.2)
    # This prevents concurrent reflections on the same agent.
    # A second transaction will block here until the first commits.
    result = await db_session.execute(
        select(Agent)
        .where(Agent.id == agent_id)
        .with_for_update()
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        logger.error("Reflection task: agent %s not found", agent_id)
        return

    # 2. Set status to reflecting
    agent.status = "reflecting"
    await db_session.flush()

    # 3. Load recent artifacts and comments
    recent_artifacts = await _load_recent_artifacts(
        agent_id, agent.last_reflection_at, db_session
    )

    if not recent_artifacts:
        logger.info("Reflection for agent %s: no recent artifacts to reflect on", agent_id)
        agent.status = "ready"
        agent.last_reflection_at = datetime.now(timezone.utc)
        await db_session.flush()
        return

    # 4. Build reflection prompt
    artifacts_section = _build_artifacts_section(recent_artifacts)
    current_skills = await _load_current_skills_text(agent_id, db_session)

    user_message = REFLECTION_USER_MSG_TEMPLATE.format(
        agent_name=agent.name,
        specialization=agent.specialization,
        artifacts_section=artifacts_section,
        current_skills=current_skills or "(none)",
    )

    # 5. Call Sonnet for reflection
    client = get_anthropic_client()
    try:
        response = await client.messages.create(
            model=settings.MODEL_SONNET,
            max_tokens=2048,
            system=REFLECTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = response.content[0].text
        reflection_data: dict[str, Any] = json.loads(raw_text)
        reflection = ReflectionResponse(**reflection_data)
    except (json.JSONDecodeError, Exception) as exc:
        logger.error(
            "Reflection LLM call failed for agent %s: %s", agent_id, exc,
        )
        # Non-fatal — just skip this reflection cycle
        agent.status = "ready"
        agent.last_reflection_at = datetime.now(timezone.utc)
        await db_session.flush()
        return

    # 6. Post-processing (TDD-03 Section 9.4)
    await _post_process_reflection(agent_id, reflection, db_session)

    # 7. Update agent metadata
    agent.last_reflection_at = datetime.now(timezone.utc)
    agent.status = "ready"

    # Recompute readiness score
    await update_agent_readiness(agent_id, db_session)

    await db_session.flush()

    logger.info(
        "Reflection completed for agent %s: %d insights, %d cautions, %d obsolete",
        agent_id,
        len(reflection.insights),
        len(reflection.cautions),
        len(reflection.obsolete_skills),
    )


# ---------------------------------------------------------------------------
# Post-processing (TDD-03 Section 9.4)
# ---------------------------------------------------------------------------


async def _post_process_reflection(
    agent_id: str,
    reflection: ReflectionResponse,
    db_session: AsyncSession,
) -> None:
    """Apply reflection results to agent's knowledge base.

    1. Insert new skill entries (insights → category 'skill')
    2. Insert new work_learning entries (cautions → category 'work_learning')
    3. Remove obsolete entries
    4. Check token budget → trigger compaction if needed
    """
    # 1. Insert insights as skill entries
    for insight in reflection.insights:
        skill = AgentSkill(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            category="skill",
            title=insight.title,
            content=insight.content,
            token_count=count_tokens(insight.content),
            source_artifact_id=insight.source_artifact,
        )
        db_session.add(skill)

    # 2. Insert cautions as work_learning entries
    for caution in reflection.cautions:
        learning = AgentSkill(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            category="work_learning",
            title=caution.title,
            content=caution.content,
            token_count=count_tokens(caution.content),
            source_artifact_id=caution.source_artifact,
        )
        db_session.add(learning)

    # 3. Remove obsolete entries
    for obsolete in reflection.obsolete_skills:
        await db_session.execute(
            delete(AgentSkill).where(
                AgentSkill.id == obsolete.skill_id,
                AgentSkill.agent_id == agent_id,
            )
        )
        logger.info(
            "Removed obsolete skill %s for agent %s: %s",
            obsolete.skill_id,
            agent_id,
            obsolete.reason,
        )

    await db_session.flush()

    # 4. Check token budget → compact if needed
    budget = await check_memory_budget(agent_id, db_session)
    if budget.over_budget:
        logger.info(
            "Agent %s over memory budget after reflection (%d/%d) — triggering compaction",
            agent_id,
            budget.total_tokens,
            budget.total_budget,
        )
        await trigger_compaction(agent_id, db_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_recent_artifacts(
    agent_id: str,
    last_reflection_at: datetime | None,
    db_session: AsyncSession,
) -> list[dict[str, Any]]:
    """Load recent approved artifacts with their comments for the reflection prompt.

    Returns a list of dicts with artifact info and comments.
    """
    query = (
        select(Artifact)
        .where(Artifact.status == "approved")
        .order_by(Artifact.approved_at.desc())
        .limit(10)
    )

    if last_reflection_at is not None:
        query = query.where(Artifact.approved_at > last_reflection_at)

    result = await db_session.execute(query)
    artifacts = result.scalars().all()

    artifact_data: list[dict[str, Any]] = []
    for artifact in artifacts:
        # Load comments for the latest version
        comments = await _load_artifact_comments(artifact.id, db_session)
        artifact_data.append({
            "id": artifact.id,
            "title": artifact.title,
            "description": artifact.description or "",
            "current_version": artifact.current_version,
            "comments": comments,
        })

    return artifact_data


async def _load_artifact_comments(
    artifact_id: str,
    db_session: AsyncSession,
) -> list[dict[str, str]]:
    """Load contextual comments for an artifact's versions."""
    result = await db_session.execute(
        select(ContextualComment)
        .join(ArtifactVersion, ArtifactVersion.id == ContextualComment.artifact_version_id)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .order_by(ContextualComment.created_at)
    )
    comments = result.scalars().all()

    return [
        {
            "highlighted_text": c.highlighted_text or "",
            "instruction": c.instruction,
            "resolved_in_version": (
                c.resolved_in_version_id if c.resolved else "unresolved"
            ),
        }
        for c in comments
    ]


def _build_artifacts_section(artifacts: list[dict[str, Any]]) -> str:
    """Build the artifacts section of the reflection prompt."""
    sections: list[str] = []
    for artifact in artifacts:
        section = (
            f"### Artifact: {artifact['title']}\n"
            f"**Brief:** {artifact['description']}\n"
            f"**Final Version:** v{artifact['current_version']}\n\n"
            f"**User Feedback (contextual comments):**"
        )
        if artifact["comments"]:
            for comment in artifact["comments"]:
                section += (
                    f'\n- Highlighted: "{comment["highlighted_text"]}"\n'
                    f'  Instruction: "{comment["instruction"]}"\n'
                    f'  Resolved in: {comment["resolved_in_version"]}'
                )
        else:
            section += "\n(no comments)"
        sections.append(section)

    return "\n\n".join(sections)


async def _load_current_skills_text(
    agent_id: str,
    db_session: AsyncSession,
) -> str:
    """Load current skill entries formatted for deduplication context."""
    result = await db_session.execute(
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
        .order_by(AgentSkill.category, AgentSkill.updated_at.desc())
    )
    entries = result.scalars().all()

    parts: list[str] = []
    for entry in entries:
        parts.append(f"[{entry.id}] {entry.category}: {entry.title}\n{entry.content}")
    return "\n\n".join(parts)


async def _recover_agent_status(
    agent_id: str,
    db_session: AsyncSession,
) -> None:
    """Set agent back to 'ready' after a reflection failure."""
    agent = await db_session.get(Agent, agent_id)
    if agent is not None:
        agent.status = "ready"
        await db_session.flush()
        logger.warning(
            "Recovered agent %s to 'ready' after reflection failure",
            agent_id,
        )
