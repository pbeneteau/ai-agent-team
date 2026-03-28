"""Agent learning task — initial skill acquisition lifecycle.

Ref: TDD-03 Section 11 (initial agent learning phase).
     TDD-03 Section 11.1 (trigger: agent creation).
     TDD-03 Section 11.2 (learning task lifecycle).
     TDD-03 Section 6.2 (tool availability: learning gets web_search, web_browser, file_write).

When an agent is created, it enters 'learning' status and this task builds
foundational knowledge via web research, stores results as agent_skills.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.anthropic_runner import AgentResult, run_agent
from app.agents.memory import count_tokens
from app.agents.readiness import update_agent_readiness
from app.config.settings import settings
from app.models.agent import Agent
from app.models.agent_skill import AgentSkill
from app.models.workspace import Workspace
from app.tools.registry import ExecutionContext, create_tool_executor, get_tools_for_phase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts (TDD-03 Section 11.2 — verbatim)
# ---------------------------------------------------------------------------

LEARNING_SYSTEM_PROMPT_TEMPLATE: str = """\
You are {agent_name}, a {specialization}. You are in your onboarding phase. \
Your goal is to build foundational knowledge about your domain so you can \
execute tasks effectively."""

LEARNING_USER_MSG_TEMPLATE: str = """\
Research your specialization in the context of this company:
{domain_description}. Tech stack: {tech_stack}.

Produce a core skills document covering:
- Key concepts and best practices in your domain
- Common patterns and conventions for this tech stack
- Industry standards and quality benchmarks

Use web_search and web_browser to research. Be thorough but concise.
Output your findings as a structured markdown document."""


# ---------------------------------------------------------------------------
# Core entry point
# ---------------------------------------------------------------------------


async def execute_learning(agent_id: str) -> None:
    """Run the full learning lifecycle for a newly created agent.

    Ref: TDD-03 Section 11.2.

    Lifecycle:
    1. Load agent from DB, set status = 'learning'
    2. Build learning prompt with workspace domain context
    3. Run agent loop with tools: web_search, web_browser, file_write
    4. Parse output → create agent_skills rows with category = 'skill'
    5. Compute readiness score
    6. Set agent.status = 'ready'
    """
    from app.core.database import async_session_maker

    async with async_session_maker() as db_session:
        try:
            await _execute_learning_impl(agent_id, db_session)
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            # On failure, ensure agent is at least set to 'ready' with
            # degraded readiness so it's not stuck in 'learning' forever
            try:
                await _recover_agent_status(agent_id, db_session)
                await db_session.commit()
            except Exception:
                logger.exception(
                    "Failed to recover agent %s status after learning failure",
                    agent_id,
                )
            raise


async def _execute_learning_impl(
    agent_id: str,
    db_session: AsyncSession,
) -> None:
    """Internal learning implementation."""
    # 1. Load agent and workspace
    agent = await db_session.get(Agent, agent_id)
    if agent is None:
        logger.error("Learning task: agent %s not found", agent_id)
        return

    workspace_result = await db_session.execute(
        select(Workspace).where(Workspace.id == agent.workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if workspace is None:
        logger.error("Learning task: workspace %s not found", agent.workspace_id)
        return

    # 2. Set status to learning
    agent.status = "learning"
    await db_session.flush()

    # 3. Build prompts
    system_prompt = LEARNING_SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=agent.name,
        specialization=agent.specialization,
    )
    user_message = LEARNING_USER_MSG_TEMPLATE.format(
        domain_description=workspace.domain_description or "Not specified",
        tech_stack=workspace.tech_stack or "Not specified",
    )

    # 4. Get tools for learning phase and create executor
    tools = get_tools_for_phase("learning")
    context = ExecutionContext(db_session=db_session)
    tool_executor = create_tool_executor(tools, context)

    # 5. Run agent loop
    result: AgentResult = await run_agent(
        system_prompt=system_prompt,
        user_message=user_message,
        tools=tools,
        model=settings.MODEL_SONNET,
        tool_executor=tool_executor,
        max_iterations=15,
        max_tokens=8192,
    )

    # 6. Parse output → create agent_skills rows
    await _store_learning_output(agent_id, result, db_session)

    # 7. Compute readiness score
    await update_agent_readiness(agent_id, db_session)

    # 8. Set status to ready
    agent.status = "ready"
    await db_session.flush()

    logger.info(
        "Learning completed for agent %s: %d input tokens, %d output tokens",
        agent_id,
        result.input_tokens,
        result.output_tokens,
    )


async def _store_learning_output(
    agent_id: str,
    result: AgentResult,
    db_session: AsyncSession,
) -> None:
    """Parse learning output and create agent_skill rows.

    The agent's text output is stored as a single 'skill' entry.
    Any files written via file_write are stored as additional skill entries.
    """
    # Store the main text output as a skill entry
    if result.text.strip():
        skill = AgentSkill(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            category="skill",
            title="Core Domain Knowledge",
            content=result.text.strip(),
            token_count=count_tokens(result.text.strip()),
        )
        db_session.add(skill)

    # Store any written files as additional skill entries
    for file_path, content in result.files.items():
        if content.strip():
            skill = AgentSkill(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                category="skill",
                title=f"Research: {file_path}",
                content=content.strip(),
                token_count=count_tokens(content.strip()),
            )
            db_session.add(skill)

    await db_session.flush()


async def _recover_agent_status(
    agent_id: str,
    db_session: AsyncSession,
) -> None:
    """Set agent to 'ready' with degraded readiness after a learning failure."""
    agent = await db_session.get(Agent, agent_id)
    if agent is not None:
        agent.status = "ready"
        agent.readiness_score = 0
        await db_session.flush()
        logger.warning(
            "Recovered agent %s to 'ready' with score 0 after learning failure",
            agent_id,
        )
