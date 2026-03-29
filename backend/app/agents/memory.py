"""Agent memory loader — loads skills and learnings into prompt context.

Ref: TDD-03 Section 5 (memory management — budget, categories, compaction).
     TDD-03 Section 5.1 (budget: 8,000 total = 6,000 skills + 2,000 learnings).
     TDD-03 Section 5.3 (compaction via Sonnet call).
     TDD-03 Section 5.4 (loading format with ## Skill: / ## Work Learning: headers).

Lifecycle: load from DB → format → check budget → compact if over → re-load → inject.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

import tiktoken
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.agent_skill import AgentSkill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Budget constants (TDD-03 Section 5.1)
# Sourced from settings for env-var tunability (Ticket 17.6).
# Module-level aliases kept for backward compat with tests and other imports.
# ---------------------------------------------------------------------------

from app.config.settings import settings as _settings

MEMORY_BUDGET_TOTAL: int = _settings.AGENT_MEMORY_BUDGET_TOTAL
MEMORY_BUDGET_SKILLS: int = _settings.AGENT_MEMORY_BUDGET_SKILLS
MEMORY_BUDGET_LEARNINGS: int = _settings.AGENT_MEMORY_BUDGET_LEARNINGS

# ---------------------------------------------------------------------------
# Token counting (TDD-03 Section 5.2)
# ---------------------------------------------------------------------------

_encoder: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken cl100k_base encoding.

    Claude's tokenizer produces similar token counts to cl100k_base.
    This is used for budget math — the pre-computed ``token_count`` column
    on ``agent_skills`` is the authoritative source for stored entries.
    """
    return len(_encoder.encode(text))


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemoryBudgetStatus:
    """Typed result from ``check_memory_budget()``."""

    skills_tokens: int
    skills_budget: int
    learnings_tokens: int
    learnings_budget: int
    total_tokens: int
    total_budget: int
    remaining: int
    over_budget: bool


# ---------------------------------------------------------------------------
# Formatting (TDD-03 Section 5.4)
# ---------------------------------------------------------------------------


def format_memory_entries(entries: Sequence[Any]) -> str:
    """Format agent skill/learning entries as markdown sections.

    Each entry must have ``.category``, ``.title``, and ``.content`` attributes.

    Skills get ``## Skill: {title}`` headers.
    Work learnings get ``## Work Learning: {title}`` headers.
    Ordering is preserved from the input sequence.
    """
    sections: list[str] = []
    for entry in entries:
        if entry.category == "skill":
            header = f"## Skill: {entry.title}"
        elif entry.category == "work_learning":
            header = f"## Work Learning: {entry.title}"
        else:
            continue
        sections.append(f"{header}\n{entry.content}")
    return "\n\n".join(sections)


def format_briefing_entries(entries: Sequence[Any]) -> str:
    """Format agent briefing entries as markdown sections.

    Briefing entries are ephemeral project context, NOT counted against
    the 8,000-token memory budget (TDD-03 Section 5.1).
    """
    sections: list[str] = []
    for entry in entries:
        sections.append(f"## Briefing: {entry.title}\n{entry.content}")
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Memory loading
# ---------------------------------------------------------------------------


async def load_agent_memory(
    agent_id: str,
    db_session: AsyncSession,
) -> str:
    """Load skills + work learnings, formatted for prompt position 4-5.

    Ref: TDD-03 Section 5.4.

    Queries ``agent_skills`` for ``skill`` and ``work_learning`` categories,
    ordered by category (skills first) then by recency (newest first).

    If the total token count exceeds the budget, triggers compaction
    automatically and re-loads.
    """
    # Check budget — compact if over before loading
    budget = await check_memory_budget(agent_id, db_session)
    if budget.over_budget:
        logger.info(
            "Agent %s memory over budget (%d/%d) — triggering compaction",
            agent_id, budget.total_tokens, budget.total_budget,
        )
        await trigger_compaction(agent_id, db_session)

    # Load entries: skills first, then learnings, each by recency
    result = await db_session.execute(
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
        .order_by(AgentSkill.category, AgentSkill.updated_at.desc())
    )
    entries = result.scalars().all()

    return format_memory_entries(entries)


async def load_agent_briefings(
    agent_id: str,
    project_id: str,
    db_session: AsyncSession,
) -> str:
    """Load briefing entries for an agent within a project context.

    Briefing entries are ephemeral project context injected separately from
    skills/learnings. They are NOT counted against the 8,000-token budget.
    """
    result = await db_session.execute(
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category == "briefing")
        .where(AgentSkill.source_artifact_id.isnot(None))
        .order_by(AgentSkill.updated_at.desc())
    )
    entries = result.scalars().all()

    return format_briefing_entries(entries)


# ---------------------------------------------------------------------------
# Budget checking
# ---------------------------------------------------------------------------


async def check_memory_budget(
    agent_id: str,
    db_session: AsyncSession,
) -> MemoryBudgetStatus:
    """Return the current memory budget status for an agent.

    Sums pre-computed ``token_count`` values from ``agent_skills`` rows,
    broken down by category (skill vs work_learning).
    """
    # Sum tokens per category
    result = await db_session.execute(
        select(AgentSkill.category, func.coalesce(func.sum(AgentSkill.token_count), 0))
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
        .group_by(AgentSkill.category)
    )
    totals: dict[str, int] = {row[0]: int(row[1]) for row in result.all()}

    skills_tokens = totals.get("skill", 0)
    learnings_tokens = totals.get("work_learning", 0)
    total_tokens = skills_tokens + learnings_tokens

    return MemoryBudgetStatus(
        skills_tokens=skills_tokens,
        skills_budget=MEMORY_BUDGET_SKILLS,
        learnings_tokens=learnings_tokens,
        learnings_budget=MEMORY_BUDGET_LEARNINGS,
        total_tokens=total_tokens,
        total_budget=MEMORY_BUDGET_TOTAL,
        remaining=max(0, MEMORY_BUDGET_TOTAL - total_tokens),
        over_budget=total_tokens > MEMORY_BUDGET_TOTAL,
    )


# ---------------------------------------------------------------------------
# Compaction (TDD-03 Section 5.3)
# ---------------------------------------------------------------------------

COMPACTION_SYSTEM_PROMPT: str = """\
You are a Knowledge Compactor. Your job is to compress an AI agent's accumulated \
skills and learnings into a tighter, higher-signal summary without losing \
important information.

Rules:
- Merge entries that cover the same topic.
- Remove entries that contradict each other (keep the more recent one).
- Remove entries that are obvious or generic (e.g., "write clearly" — every \
agent should do this).
- Preserve specific, hard-won knowledge: user preferences, brand voice rules, \
domain-specific conventions, technical patterns, past corrections.
- The output must be strictly smaller than the input (target: 60-70% of \
original token count).
- Maintain the same markdown format (## headers, bullet points).
- Do NOT invent new knowledge. Only consolidate what exists."""

_COMPACTED_SKILLS_MARKER = "### COMPACTED SKILLS"
_COMPACTED_LEARNINGS_MARKER = "### COMPACTED WORK LEARNINGS"


async def trigger_compaction(
    agent_id: str,
    db_session: AsyncSession,
) -> None:
    """Run a compaction cycle on the agent's memory.

    Ref: TDD-03 Section 5.3.

    1. Load all skill + work_learning entries.
    2. Call Sonnet to merge/deduplicate/distill.
    3. Delete old entries, insert compacted replacements.
    4. If still over budget after compaction, hard-truncate oldest learnings.
    """
    from app.agents.anthropic_runner import run_agent
    from app.agents.telemetry import CompactionMetrics, Timer, emit_compaction_metrics
    from app.models.agent import Agent

    compaction_timer = Timer()
    compaction_timer.__enter__()

    # Load the agent for name/specialization
    agent_result = await db_session.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        logger.error("Cannot compact memory: agent %s not found", agent_id)
        return

    # Load all current entries
    entries_result = await db_session.execute(
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
        .order_by(AgentSkill.category, AgentSkill.updated_at.desc())
    )
    entries = entries_result.scalars().all()

    if not entries:
        return

    # Compute current token counts by category
    skill_entries = [e for e in entries if e.category == "skill"]
    learning_entries = [e for e in entries if e.category == "work_learning"]
    skill_tokens = sum(e.token_count for e in skill_entries)
    learning_tokens = sum(e.token_count for e in learning_entries)
    before_tokens = skill_tokens + learning_tokens
    entries_before = len(entries)

    # Format entries for the compaction prompt
    skills_text = "\n\n".join(
        f"## {e.title}\n{e.content}" for e in skill_entries
    ) or "(none)"
    learnings_text = "\n\n".join(
        f"## {e.title}\n{e.content}" for e in learning_entries
    ) or "(none)"

    user_message = (
        f"## Agent: {agent.name} ({agent.specialization})\n\n"
        f"## Current Skills ({skill_tokens} tokens)\n{skills_text}\n\n"
        f"## Current Work Learnings ({learning_tokens} tokens)\n{learnings_text}\n\n"
        f"Compact these into a single skills document and a single work learnings document.\n"
        f"Target total: {MEMORY_BUDGET_TOTAL} tokens maximum.\n\n"
        f"Output format:\n"
        f"{_COMPACTED_SKILLS_MARKER}\n"
        f"{{compacted skills content}}\n\n"
        f"{_COMPACTED_LEARNINGS_MARKER}\n"
        f"{{compacted work learnings content}}"
    )

    # Call Sonnet for compaction
    try:
        result = await run_agent(
            system_prompt=COMPACTION_SYSTEM_PROMPT,
            user_message=user_message,
            tools=[],
            model=settings.MODEL_SONNET,
            max_iterations=1,
            max_tokens=4096,
        )
    except Exception:
        logger.exception("Compaction LLM call failed for agent %s", agent_id)
        return

    # Parse compacted output
    compacted_skills, compacted_learnings = _parse_compaction_output(result.text)

    # Delete all existing skill + work_learning entries
    await db_session.execute(
        delete(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
    )

    # Insert compacted entries
    if compacted_skills.strip():
        await db_session.execute(
            AgentSkill.__table__.insert().values(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                category="skill",
                title="Compacted Skills",
                content=compacted_skills.strip(),
                token_count=count_tokens(compacted_skills.strip()),
            )
        )

    if compacted_learnings.strip():
        await db_session.execute(
            AgentSkill.__table__.insert().values(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                category="work_learning",
                title="Compacted Work Learnings",
                content=compacted_learnings.strip(),
                token_count=count_tokens(compacted_learnings.strip()),
            )
        )

    await db_session.flush()

    # Post-compaction budget check — hard-truncate learnings if still over
    budget = await check_memory_budget(agent_id, db_session)
    if budget.over_budget:
        logger.warning(
            "Agent %s still over budget after compaction (%d/%d) — "
            "truncating oldest work_learnings",
            agent_id, budget.total_tokens, budget.total_budget,
        )
        await _hard_truncate_learnings(agent_id, db_session)

    # Emit compaction telemetry (Ticket 16.1)
    compaction_timer.__exit__(None, None, None)
    post_budget = await check_memory_budget(agent_id, db_session)
    # Count remaining entries
    remaining_result = await db_session.execute(
        select(func.count(AgentSkill.id))
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
    )
    entries_after = int(remaining_result.scalar_one())

    emit_compaction_metrics(CompactionMetrics(
        agent_id=agent_id,
        before_tokens=before_tokens,
        after_tokens=post_budget.total_tokens,
        entries_before=entries_before,
        entries_after=entries_after,
        elapsed_seconds=compaction_timer.elapsed,
    ))


def _parse_compaction_output(text: str) -> tuple[str, str]:
    """Parse the compaction LLM output into (skills, learnings) sections.

    Splits on the ``### COMPACTED SKILLS`` and ``### COMPACTED WORK LEARNINGS``
    markers. Returns empty strings for missing sections.
    """
    skills = ""
    learnings = ""

    # Case-insensitive search for markers
    skills_match = re.search(
        r"###\s*COMPACTED\s+SKILLS\s*\n(.*?)(?=###\s*COMPACTED\s+WORK\s+LEARNINGS|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    learnings_match = re.search(
        r"###\s*COMPACTED\s+WORK\s+LEARNINGS\s*\n(.*)",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if skills_match:
        skills = skills_match.group(1).strip()
    if learnings_match:
        learnings = learnings_match.group(1).strip()

    return skills, learnings


async def _hard_truncate_learnings(
    agent_id: str,
    db_session: AsyncSession,
) -> None:
    """Delete work_learning entries from oldest until under budget.

    Last resort after compaction fails to bring memory under the ceiling.
    """
    # Get all learning entries ordered oldest first
    result = await db_session.execute(
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category == "work_learning")
        .order_by(AgentSkill.updated_at.asc())
    )
    learnings = list(result.scalars().all())

    # Get current skill token total
    skill_result = await db_session.execute(
        select(func.coalesce(func.sum(AgentSkill.token_count), 0))
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category == "skill")
    )
    skill_tokens: int = int(skill_result.scalar_one())

    # Delete from oldest until under budget
    running_learning_tokens = sum(e.token_count for e in learnings)
    for entry in learnings:
        if skill_tokens + running_learning_tokens <= MEMORY_BUDGET_TOTAL:
            break
        running_learning_tokens -= entry.token_count
        await db_session.execute(
            delete(AgentSkill).where(AgentSkill.id == entry.id)
        )
        logger.info("Hard-truncated work_learning '%s' for agent %s", entry.title, agent_id)

    await db_session.flush()
