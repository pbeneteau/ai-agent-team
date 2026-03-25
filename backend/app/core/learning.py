"""
Agent learning phase.
Each agent researches its domain, learns the project context,
writes its skills as Markdown files, and sets up its workspace.
"""
import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from app.config import get_settings, has_web_search
from app.config.prompts import (
    AGENT_REFLECTION_PROMPT,
    CONSOLIDATE_CORE_SKILLS_PROMPT,
    DOCUMENT_REBRIEFING_PROMPT,
    LEARNING_SYSTEM_PROMPT,
    LEARN_FROM_WORK_PROMPT,
    LEARN_FROM_WORK_SCHEMA_HINT,
    PROJECT_BRIEFING_PROMPT,
    TARGETED_REBRIEFING_PROMPT,
)
from app.config.token_budgets import (
    CORE_SKILLS_CONSOLIDATION_MAX_TOKENS,
    CORE_SKILLS_CONSOLIDATION_THRESHOLD,
    EPISODES_MAX_ENTRIES,
    PROJECT_CONTEXT_BRIEFING_MAX_TOKENS,
    REFLECTION_MAX_TOKENS,
    REFLECTION_TRIGGER_THRESHOLD,
    WORK_LEARNINGS_EXISTING_BUDGET,
    WORK_LEARNINGS_RESULT_BUDGET,
)
from app.core.knowledge import get_knowledge_audit_service
from app.core.project_brief import render_project_brief_summary
from app.core.structured_json import StructuredJsonError, request_structured_json_async
from app.core.workspace import get_workspace_manager
from app.models.agent import (
    AgentConfig,
    AgentOccupancyReason,
    AgentOccupancyStatus,
    AgentStatus,
    build_agent_status_payload,
)
from app.core.agent_factory import get_agent_factory
from app.memory.project_context import get_project_context_store
from app.core.usage_tracker import get_usage_tracker
from app.models.task import TaskExecutionNode, TaskResponse
from app.tools.registry import consolidate_skill_content

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _broadcast_agent_status(agent_id: str, broadcast_callback=None):
    if not broadcast_callback:
        return
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        return
    await broadcast_callback({"type": "agent_status", "data": build_agent_status_payload(agent)})

WORK_LEARNINGS_SKILL = "work_learnings"
_WORK_LEARNINGS_MAX_INSIGHTS_PER_NODE = 3
_WORK_LEARNINGS_MAX_CAUTIONS_PER_NODE = 2
_WORK_LEARNINGS_MAX_INSIGHT_ITEMS = 18
_WORK_LEARNINGS_MAX_CAUTION_ITEMS = 12
_WORK_LEARNINGS_ITEM_MAX_CHARS = 280
_WORK_LEARNINGS_CONSOLIDATE_AT = 4200
_WORK_LEARNINGS_MAX_CHARS = 5000


class _WorkLearningsPayload(BaseModel):
    insights: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


def _strip_skill_header(content: str) -> str:
    stripped = (content or "").lstrip()
    if not stripped.startswith("<!--"):
        return content or ""
    end = stripped.find("-->")
    if end == -1:
        return content or ""
    return stripped[end + 3:].lstrip()


def _sanitize_work_learning_item(item: str) -> str:
    text = re.sub(r"\s+", " ", str(item or "")).strip()
    text = text.lstrip("-*• ").strip()
    if ":" in text:
        prefix, remainder = text.split(":", 1)
        if prefix.strip().lower() in {"insight", "caution"}:
            text = remainder.strip()
    return text[:_WORK_LEARNINGS_ITEM_MAX_CHARS].strip()


def _normalize_work_learning_item(item: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", item.lower()).strip()


def _merge_work_learning_items(existing: list[str], incoming: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    incoming_items = [_sanitize_work_learning_item(candidate) for candidate in incoming]

    for item in incoming_items + existing:
        normalized = _normalize_work_learning_item(item)
        if len(item) < 12 or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(item)
        if len(merged) >= limit:
            break

    return merged


def _parse_work_learnings(content: str) -> tuple[list[str], list[str]]:
    insights: list[str] = []
    cautions: list[str] = []
    current_section = "insights"
    in_comment_block = False

    for raw_line in _strip_skill_header(content).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("<!--"):
            in_comment_block = True
        if in_comment_block:
            if "-->" in line:
                in_comment_block = False
            continue

        lower = line.lower()
        if lower.startswith("## "):
            if "verified reusable insights" in lower:
                current_section = "insights"
            elif "reusable cautions" in lower:
                current_section = "cautions"
            else:
                current_section = "insights"
            continue

        if not line.startswith(("-", "*", "•")):
            continue

        item = line.lstrip("-*• ").strip()
        target = current_section
        if item.lower().startswith("caution:"):
            target = "cautions"
        elif item.lower().startswith("insight:"):
            target = "insights"

        sanitized = _sanitize_work_learning_item(item)
        if not sanitized:
            continue

        if target == "cautions":
            cautions.append(sanitized)
        else:
            insights.append(sanitized)

    return insights, cautions


def _format_work_learnings(insights: list[str], cautions: list[str]) -> str:
    parts = [
        "# Work Learnings",
        "",
        "Durable, role-specific learnings extracted from completed work.",
        "",
        "## Verified reusable insights",
    ]
    if insights:
        parts.extend(f"- {item}" for item in insights)
    else:
        parts.append("No durable insights captured yet.")

    parts.extend([
        "",
        "## Reusable cautions",
    ])
    if cautions:
        parts.extend(f"- {item}" for item in cautions)
    else:
        parts.append("No reusable cautions captured yet.")

    return "\n".join(parts).strip() + "\n"


def _compact_work_learnings_content(insights: list[str], cautions: list[str], workspace_path: str) -> str:
    content = _format_work_learnings(insights, cautions)
    if len(content) > _WORK_LEARNINGS_CONSOLIDATE_AT:
        consolidated = consolidate_skill_content(WORK_LEARNINGS_SKILL, content, workspace_path)
        if consolidated:
            reparsed_insights, reparsed_cautions = _parse_work_learnings(consolidated)
            insights = _merge_work_learning_items([], reparsed_insights, _WORK_LEARNINGS_MAX_INSIGHT_ITEMS)
            cautions = _merge_work_learning_items([], reparsed_cautions, _WORK_LEARNINGS_MAX_CAUTION_ITEMS)
            content = _format_work_learnings(insights, cautions)

    while len(content) > _WORK_LEARNINGS_MAX_CHARS and (len(insights) > 1 or len(cautions) > 1):
        if len(insights) >= len(cautions) and len(insights) > 1:
            insights = insights[:-1]
        elif len(cautions) > 1:
            cautions = cautions[:-1]
        else:
            insights = insights[:-1]
        content = _format_work_learnings(insights, cautions)

    return content


_SEMANTIC_DEDUP_DISTANCE_THRESHOLD = 0.30  # L2 distance — ~cosine sim > 0.85


def _is_semantically_duplicate(text: str, collection_name: str) -> bool:
    """Check if text is semantically similar to any existing entry via ChromaDB."""
    try:
        from app.memory.vector_store import get_vector_store
        vs = get_vector_store()
        results = vs.query(collection_name, [text], n_results=1)
        if not results:
            return False
        return results[0].get("distance", 999) < _SEMANTIC_DEDUP_DISTANCE_THRESHOLD
    except Exception:
        return False


def _check_and_migrate_team_learnings(
    agent: AgentConfig,
    new_insights: list[str],
    new_cautions: list[str],
) -> None:
    """Check new learnings against other agents in the same team. Migrate duplicates to shared team knowledge."""
    if not agent.team_id:
        return

    factory = get_agent_factory()
    team_agents = factory.get_team_agents(agent.team_id)
    if len(team_agents) < 2:
        return

    # Collect normalized learnings from all other agents in the team
    other_normalized: set[str] = set()
    for other in team_agents:
        if other.id == agent.id:
            continue
        other_ws = get_workspace_manager().get(other.id, other.name, other.title)
        other_content = other_ws.read_skill(WORK_LEARNINGS_SKILL) or ""
        other_insights, other_cautions = _parse_work_learnings(other_content)
        for item in other_insights + other_cautions:
            other_normalized.add(_normalize_work_learning_item(item))

    # Index other agents' learnings in ChromaDB for semantic matching
    collection_name = f"team_learnings_{agent.team_id}"
    other_raw_items: list[str] = []
    for other in team_agents:
        if other.id == agent.id:
            continue
        other_ws = get_workspace_manager().get(other.id, other.name, other.title)
        other_content = other_ws.read_skill(WORK_LEARNINGS_SKILL) or ""
        other_ins, other_cau = _parse_work_learnings(other_content)
        other_raw_items.extend(other_ins + other_cau)
    if other_raw_items:
        try:
            from app.memory.vector_store import get_vector_store
            vs = get_vector_store()
            ids = [f"tl_{hash(i) & 0xFFFFFFFF:08x}" for i in other_raw_items]
            vs.upsert(collection_name, documents=other_raw_items, ids=ids)
        except Exception:
            pass

    # Find matches
    shared_insights: list[str] = []
    shared_cautions: list[str] = []
    for item in new_insights:
        if _normalize_work_learning_item(item) in other_normalized:
            shared_insights.append(item)
    for item in new_cautions:
        if _normalize_work_learning_item(item) in other_normalized:
            shared_cautions.append(item)

    # Semantic dedup pass — catch paraphrases missed by exact normalization
    for item in new_insights:
        if _normalize_work_learning_item(item) not in other_normalized:
            if _is_semantically_duplicate(item, collection_name):
                shared_insights.append(item)
    for item in new_cautions:
        if _normalize_work_learning_item(item) not in other_normalized:
            if _is_semantically_duplicate(item, collection_name):
                shared_cautions.append(item)

    if not shared_insights and not shared_cautions:
        return

    # Write to team knowledge file
    shared_ws = get_workspace_manager().shared
    skill_name = f"team_knowledge_{agent.team_id}"
    existing = shared_ws.read_skill(skill_name) or ""
    existing_normalized: set[str] = set()
    for line in existing.splitlines():
        stripped = line.strip().lstrip("-*• ").strip()
        if stripped:
            existing_normalized.add(_normalize_work_learning_item(stripped))

    date_tag = datetime.now(UTC).strftime("%Y-%m-%d")
    new_lines: list[str] = []
    for item in shared_insights:
        if _normalize_work_learning_item(item) not in existing_normalized:
            new_lines.append(f"- {item} ({date_tag})")
            existing_normalized.add(_normalize_work_learning_item(item))
    for item in shared_cautions:
        if _normalize_work_learning_item(item) not in existing_normalized:
            new_lines.append(f"- Caution: {item} ({date_tag})")
            existing_normalized.add(_normalize_work_learning_item(item))

    if not new_lines:
        return

    if existing and _strip_skill_header(existing).strip():
        content = _strip_skill_header(existing).rstrip() + "\n" + "\n".join(new_lines) + "\n"
    else:
        content = (
            "# Team Knowledge\n\n"
            "Shared learnings validated by multiple team members.\n\n"
            + "\n".join(new_lines) + "\n"
        )

    # Consolidate if team knowledge exceeds 2000 chars
    if len(content) > 2000:
        consolidated = consolidate_skill_content(skill_name, content, str(shared_ws.root))
        if consolidated:
            content = consolidated

    shared_ws.write_skill(skill_name, content, author=f"team_dedup:{agent.id}")
    logger.info("Team knowledge updated for team %s: +%d shared items", agent.team_id, len(new_lines))

    # Index new team knowledge items in ChromaDB
    try:
        from app.memory.vector_store import get_vector_store
        vs = get_vector_store()
        raw_items = [l.lstrip("- ").rstrip(f" ({date_tag})") for l in new_lines]
        ids = [f"tl_{hash(i) & 0xFFFFFFFF:08x}" for i in raw_items]
        vs.upsert(collection_name, documents=raw_items, ids=ids)
    except Exception:
        pass


def _read_agent_stats(workspace) -> dict:
    """Read agent_stats.json from the workspace skills directory."""
    try:
        raw = workspace.read_skill("agent_stats")
        if raw:
            content = _strip_skill_header(raw).strip()
            return json.loads(content)
    except Exception:
        pass
    return {}


def _write_agent_stats(workspace, stats: dict) -> None:
    """Write agent_stats.json to the workspace skills directory."""
    path = workspace.skills / "agent_stats.json"
    path.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")


async def consolidate_core_skills(agent: AgentConfig) -> bool:
    """Merge durable work_learnings into core_skills via a single Claude call."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return False

    workspace = get_workspace_manager().get(agent.id, agent.name, agent.title)
    core_skills = workspace.read_skill("core_skills")
    work_learnings = workspace.read_skill("work_learnings")
    if not core_skills or not work_learnings:
        return False

    prompt = CONSOLIDATE_CORE_SKILLS_PROMPT.format(
        agent_name=agent.name,
        agent_title=agent.title,
        agent_specialization=agent.specialization,
        core_skills=_strip_skill_header(core_skills),
        work_learnings=_strip_skill_header(work_learnings),
    )

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=CORE_SKILLS_CONSOLIDATION_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        get_usage_tracker().log(settings.claude_model, response.usage.input_tokens, response.usage.output_tokens)
        result = response.content[0].text.strip()
        if not result or len(result) < 100:
            return False
        workspace.write_skill("core_skills", result, author="consolidation")
        get_knowledge_audit_service().invalidate_agent(agent.id)
        logger.info("Core skills consolidated for %s (threshold=%d)", agent.name, CORE_SKILLS_CONSOLIDATION_THRESHOLD)
        return True
    except Exception as exc:
        logger.warning("Core skills consolidation failed for %s: %s", agent.name, exc)
        return False


def write_episode(
    agent: AgentConfig,
    task: TaskResponse,
    nodes: list[TaskExecutionNode],
) -> None:
    """Write a structured episode entry to the agent's episodes.md after task completion."""
    workspace = get_workspace_manager().get(agent.id, agent.name, agent.title)

    # Compute aggregate stats
    quality_scores = [n.quality_score for n in nodes if n.quality_score is not None]
    avg_quality = round(sum(quality_scores) / len(quality_scores)) if quality_scores else None
    warnings_list = []
    for n in nodes:
        warnings_list.extend(n.warnings[:2])

    # Compute duration from earliest start to latest completion
    started_times = [n.started_at for n in nodes if n.started_at]
    completed_times = [n.completed_at for n in nodes if n.completed_at]
    duration = ""
    if started_times and completed_times:
        try:
            start = min(datetime.fromisoformat(t) for t in started_times)
            end = max(datetime.fromisoformat(t) for t in completed_times)
            delta = end - start
            total_secs = int(delta.total_seconds())
            if total_secs >= 3600:
                duration = f"{total_secs // 3600}h {(total_secs % 3600) // 60}m"
            elif total_secs >= 60:
                duration = f"{total_secs // 60}m {total_secs % 60}s"
            else:
                duration = f"{total_secs}s"
        except Exception:
            pass

    quality_str = f"{avg_quality}/100" if avg_quality is not None else "N/A"
    result_summary = (task.result or "N/A")[:300].replace("\n", " ")
    issues_str = "; ".join(warnings_list[:4]) if warnings_list else "None"

    entry = (
        f"### {task.title}\n"
        f"- **Date:** {task.updated_at[:10] if task.updated_at else 'unknown'}\n"
        f"- **Quality:** {quality_str}\n"
        f"- **Duration:** {duration or 'N/A'}\n"
        f"- **Result summary:** {result_summary}\n"
        f"- **Issues:** {issues_str}\n"
        f"- **Status:** {task.status.value}\n"
    )

    # Read existing episodes and prepend (most recent first)
    existing = workspace.read_skill("episodes") or ""
    existing_body = _strip_skill_header(existing).strip()

    # Parse existing entries and trim to max
    if existing_body:
        # Split by ### headers
        entries = [e.strip() for e in re.split(r"(?=^### )", existing_body, flags=re.MULTILINE) if e.strip()]
        entries = entries[:EPISODES_MAX_ENTRIES - 1]  # leave room for new entry
        content = "# Task History\n\n" + entry + "\n" + "\n".join(entries) + "\n"
    else:
        content = "# Task History\n\n" + entry

    workspace.write_skill("episodes", content, author="episode_writer")
    logger.info("Episode written for %s: %s", agent.name, task.title)


async def run_agent_reflection(agent: AgentConfig, broadcast_callback=None) -> bool:
    """Periodic self-reflection: agent rereads all memory and updates core_skills with durable patterns."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return False

    workspace = get_workspace_manager().get(agent.id, agent.name, agent.title)
    core_skills = workspace.read_skill("core_skills") or ""
    work_learnings = workspace.read_skill("work_learnings") or ""
    episodes = workspace.read_skill("episodes") or ""

    # Read team knowledge if available
    team_knowledge = ""
    if agent.team_id:
        shared_ws = get_workspace_manager().shared
        team_knowledge = shared_ws.read_skill(f"team_knowledge_{agent.team_id}") or ""

    if not core_skills and not work_learnings:
        return False

    prompt = AGENT_REFLECTION_PROMPT.format(
        agent_name=agent.name,
        agent_title=agent.title,
        agent_specialization=agent.specialization,
        core_skills=_strip_skill_header(core_skills),
        work_learnings=_strip_skill_header(work_learnings) or "None yet.",
        episodes=_strip_skill_header(episodes) or "No episodes yet.",
        team_knowledge=_strip_skill_header(team_knowledge) or "None.",
    )

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=REFLECTION_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        get_usage_tracker().log(settings.claude_model, response.usage.input_tokens, response.usage.output_tokens)
        result = response.content[0].text.strip()
        if not result or len(result) < 100:
            return False

        workspace.write_skill("core_skills", result, author="reflection")
        get_knowledge_audit_service().invalidate_agent(agent.id)

        # Update stats
        stats = _read_agent_stats(workspace)
        stats["last_reflection_at"] = _now_iso()
        _write_agent_stats(workspace, stats)

        logger.info("Reflection complete for %s — core_skills updated", agent.name)

        if broadcast_callback:
            await broadcast_callback({
                "type": "reflection_complete",
                "data": {"agent_id": agent.id, "agent_name": agent.name},
            })
        return True
    except Exception as exc:
        logger.warning("Reflection failed for %s: %s", agent.name, exc)
        return False


async def run_learn_from_work(
    agent: AgentConfig,
    task: TaskResponse,
    node: TaskExecutionNode,
    broadcast_callback=None,
) -> bool:
    if not (node.result or "").strip():
        return False

    settings = get_settings()
    if not settings.anthropic_api_key:
        return False

    workspace = get_workspace_manager().get(agent.id, agent.name, agent.title)
    existing_content = workspace.read_skill(WORK_LEARNINGS_SKILL) or ""

    prompt = LEARN_FROM_WORK_PROMPT.format(
        agent_name=agent.name,
        agent_title=agent.title,
        agent_specialization=agent.specialization,
        task_title=task.title,
        task_description=task.description.strip()[:1200],
        node_title=node.title,
        node_description=node.description.strip()[:1200],
        node_result=(node.result or "").strip()[:WORK_LEARNINGS_RESULT_BUDGET],
        sources="\n".join(f"- {source}" for source in node.sources[:8]) or "- None",
        assumptions="\n".join(f"- {assumption}" for assumption in node.assumptions[:6]) or "- None",
        warnings="\n".join(f"- {warning}" for warning in node.warnings[:6]) or "- None",
        existing_work_learnings=_strip_skill_header(existing_content)[:WORK_LEARNINGS_EXISTING_BUDGET] or "None yet.",
        node_status=node.status.value,
        quality_score=node.quality_score if node.quality_score is not None else "N/A",
    )

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        structured = await request_structured_json_async(
            client=client,
            model=settings.claude_model,
            prompt=prompt,
            response_model=_WorkLearningsPayload,
            schema_hint=LEARN_FROM_WORK_SCHEMA_HINT,
            max_tokens=700,
            repair_max_tokens=500,
            request_name=f"learn_from_work:{agent.id}:{node.id}",
        )
        payload = structured.value.model_dump(mode="json")
    except StructuredJsonError as exc:
        logger.warning(
            "Learn-from-work synthesis failed for %s on node %s: %s (preview=%r, parse_error=%s, repair_error=%s)",
            agent.name,
            node.id,
            exc,
            exc.telemetry.raw_preview,
            exc.telemetry.parse_error,
            exc.telemetry.repair_error,
        )
        return False
    except Exception as exc:
        logger.warning("Learn-from-work synthesis failed for %s on node %s: %s", agent.name, node.id, exc)
        return False

    raw_insights = payload.get("insights") if isinstance(payload.get("insights"), list) else []
    raw_cautions = payload.get("cautions") if isinstance(payload.get("cautions"), list) else []
    new_insights = _merge_work_learning_items([], [str(item) for item in raw_insights], _WORK_LEARNINGS_MAX_INSIGHTS_PER_NODE)
    new_cautions = _merge_work_learning_items([], [str(item) for item in raw_cautions], _WORK_LEARNINGS_MAX_CAUTIONS_PER_NODE)
    if not new_insights and not new_cautions:
        return False

    existing_insights, existing_cautions = _parse_work_learnings(existing_content)
    merged_insights = _merge_work_learning_items(
        existing_insights,
        new_insights,
        _WORK_LEARNINGS_MAX_INSIGHT_ITEMS,
    )
    merged_cautions = _merge_work_learning_items(
        existing_cautions,
        new_cautions,
        _WORK_LEARNINGS_MAX_CAUTION_ITEMS,
    )
    final_content = _compact_work_learnings_content(merged_insights, merged_cautions, str(workspace.root))
    workspace.write_skill(WORK_LEARNINGS_SKILL, final_content, author=f"learn_from_work:{node.id}")
    get_knowledge_audit_service().invalidate_agent(agent.id)

    # Check for cross-agent duplicate learnings and migrate to team knowledge
    try:
        _check_and_migrate_team_learnings(agent, new_insights, new_cautions)
    except Exception as exc:
        logger.debug("Team knowledge migration failed for %s: %s", agent.name, exc)

    logger.info(
        "Work learnings updated for %s: +%s insight(s), +%s caution(s)",
        agent.name,
        len(new_insights),
        len(new_cautions),
    )

    # Track completed task nodes and trigger core_skills consolidation periodically
    stats = _read_agent_stats(workspace)
    stats["completed_task_nodes"] = stats.get("completed_task_nodes", 0) + 1
    _write_agent_stats(workspace, stats)
    if stats["completed_task_nodes"] % CORE_SKILLS_CONSOLIDATION_THRESHOLD == 0:
        logger.info("Triggering core_skills consolidation for %s (node count=%d)", agent.name, stats["completed_task_nodes"])
        await consolidate_core_skills(agent)

    if stats["completed_task_nodes"] % REFLECTION_TRIGGER_THRESHOLD == 0:
        logger.info("Triggering periodic reflection for %s (node count=%d)", agent.name, stats["completed_task_nodes"])
        await run_agent_reflection(agent)

    return True


def _build_project_summary(ctx: dict) -> str:
    return render_project_brief_summary(ctx, include_meta=True)


def _project_context_skill_metadata(ctx_store) -> dict[str, str]:
    active_brief = ctx_store.get_active_brief()
    metadata = {"projection": "role_brief"}
    if not active_brief:
        return metadata
    metadata["brief_revision"] = str(active_brief.revision)
    metadata["brief_fingerprint"] = active_brief.brief_fingerprint
    return metadata


def _write_project_context_projection(workspace, ctx_store, content: str, *, author: str) -> None:
    workspace.write_skill(
        "project_context",
        content,
        author=author,
        metadata=_project_context_skill_metadata(ctx_store),
    )


async def run_learning_phase(agent: AgentConfig, broadcast_callback=None) -> bool:
    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    factory.update_agent_status(agent.id, AgentStatus.LEARNING)
    factory.update_agent_occupancy(
        agent.id,
        occupancy_status=AgentOccupancyStatus.BUSY,
        occupancy_reason=AgentOccupancyReason.LEARNING,
        current_task_title="Phase d'apprentissage",
        busy_since=_now_iso(),
    )
    await _broadcast_agent_status(agent.id, broadcast_callback)

    try:
        from app.core.workspace import get_workspace_manager
        wm = get_workspace_manager()
        workspace = wm.get(agent.id, agent.name, agent.title)
        workspace_path = str(workspace.root)

        project_ctx = ctx_store.load_context() or {}
        project_summary = _build_project_summary(project_ctx)

        # Use the agent's actual model tier for learning: leads get Opus, specialists get Sonnet
        from app.models.agent import ModelTier
        learning_model = (
            settings.claude_model_opus
            if agent.model_tier == ModelTier.OPUS
            else settings.claude_model
        )

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        system_prompt = LEARNING_SYSTEM_PROMPT.format(
            agent_name=agent.name,
            agent_title=agent.title,
            project_context=project_summary,
            workspace_path=workspace_path,
        )

        response = await client.messages.create(
            model=learning_model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Write both documents for your role as {agent.title}.\n"
                    f"Specialization: {agent.specialization}\n"
                    f"Goal: {agent.goal}\n\n"
                    f"Backstory: {agent.backstory}\n\n"
                    "Separate the two documents clearly with:\n"
                    "## DOCUMENT: core_skills\n(content)\n\n## DOCUMENT: project_context\n(content)"
                ),
            }],
        )

        get_usage_tracker().log(learning_model, response.usage.input_tokens, response.usage.output_tokens)
        raw = response.content[0].text
        # Split the two documents
        core_skills_content, project_ctx_content = _split_learning_output(raw)

        workspace.write_skill("core_skills", core_skills_content, author="learning_phase")
        _write_project_context_projection(
            workspace,
            ctx_store,
            project_ctx_content,
            author="learning_phase",
        )
        workspace.write_profile({
            "id": agent.id,
            "name": agent.name,
            "title": agent.title,
            "specialization": agent.specialization,
            "goal": agent.goal,
            "team_id": agent.team_id,
            "workspace_path": workspace_path,
        })

        workspace.write(
            "output/profile.md",
            f"# {agent.name} — {agent.title}\n\n"
            f"**Specialization:** {agent.specialization}\n"
            f"**Goal:** {agent.goal}\n"
            f"**Workspace:** `{workspace_path}`\n\n"
            f"## Backstory\n\n{agent.backstory}\n",
        )

        ctx_store.index_text(
            text=f"{agent.name} ({agent.title}): {agent.goal}\n{core_skills_content[:500]}",
            doc_id=f"agent_{agent.id}",
            metadata={"type": "agent", "agent_id": agent.id, "title": agent.title},
        )
        get_knowledge_audit_service().invalidate_agent(agent.id)

        factory.update_agent_status(agent.id, AgentStatus.READY)
        factory.clear_agent_occupancy(agent.id)
        await _broadcast_agent_status(agent.id, broadcast_callback)
        logger.info(f"Agent {agent.name} learning complete — workspace: {workspace_path}")
        return True

    except Exception as e:
        logger.exception(f"Learning phase failed for {agent.name}: {e}")
        factory.update_agent_status(agent.id, AgentStatus.ERROR)
        factory.clear_agent_occupancy(agent.id)
        await _broadcast_agent_status(agent.id, broadcast_callback)
        return False


def _split_learning_output(raw: str) -> tuple[str, str]:
    """Split the LLM response into (core_skills, project_context) documents."""
    marker_core = "## DOCUMENT: core_skills"
    marker_ctx = "## DOCUMENT: project_context"

    core = ""
    project = ""

    if marker_core in raw and marker_ctx in raw:
        idx_core = raw.index(marker_core) + len(marker_core)
        idx_ctx = raw.index(marker_ctx)
        core = raw[idx_core:idx_ctx].strip()
        project = raw[raw.index(marker_ctx) + len(marker_ctx):].strip()
    else:
        # Fallback: put everything in core_skills
        core = raw
        project = "# Project Context\n\nTBD — project briefing not yet completed."

    return core, project


def _build_role_project_context_prompt(
    *,
    agent: AgentConfig,
    project_summary: str,
    source_name: str | None = None,
    source_text: str | None = None,
) -> str:
    source_block = ""
    if source_name and source_text:
        source_block = (
            f'\n## Additional source: "{source_name}"\n'
            f"{source_text[:12000]}\n"
            "- Use this source only where it adds role-relevant detail.\n"
            f'- Cite any number copied from it with "(Source: {source_name})".\n'
            "- If it conflicts with the shared brief, prefer the newer source but mention the uncertainty.\n"
        )
    return f"""You are {agent.name}, a {agent.title} in an AI agent team.

## Shared project brief
{project_summary}
{source_block}
## Your task
Write the full content of `project_context.md` for YOUR role only.

Rules:
- Focus only on what matters to a {agent.title}
- Prefer short sections and bullets over paragraphs
- Keep only execution-relevant context; cut background fluff
- Separate clearly:
  - Confirmed context
  - Role-specific implications
  - TBD / open questions
- Flag missing information as `TBD — needs verification`
- Do NOT invent numbers, market data, competitor details or projections
- Keep the file under 450 words

Write only the Markdown content. No preamble."""


async def _generate_role_project_context(
    *,
    client: AsyncAnthropic,
    model: str,
    agent: AgentConfig,
    project_summary: str,
    source_name: str | None = None,
    source_text: str | None = None,
) -> str:
    prompt = _build_role_project_context_prompt(
        agent=agent,
        project_summary=project_summary,
        source_name=source_name,
        source_text=source_text,
    )
    response = await client.messages.create(
        model=model,
        max_tokens=PROJECT_CONTEXT_BRIEFING_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    get_usage_tracker().log(model, response.usage.input_tokens, response.usage.output_tokens)
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip()


async def run_project_briefing(team_id: str, broadcast_callback=None):
    """
    After the user provides rich project context, Alex writes a domain-scoped
    project_context.md to each agent's workspace. This can be run multiple times
    as the project evolves.
    """
    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    project_ctx = ctx_store.load_context() or {}
    if not project_ctx:
        logger.warning("No project context found — skipping briefing")
        return

    agents = factory.get_team_agents(team_id)
    if not agents:
        return

    project_summary = _build_project_summary(project_ctx)
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    updated = 0
    for agent in agents:
        try:
            content = await _generate_role_project_context(
                client=client,
                model=settings.claude_model,
                agent=agent,
                project_summary=project_summary,
            )
        except Exception as exc:
            logger.exception("Project briefing generation failed for %s: %s", agent.name, exc)
            continue
        if not content:
            logger.warning("Project briefing returned empty content for %s", agent.name)
            continue
        workspace = get_workspace_manager().get(agent.id, agent.name, agent.title)
        _write_project_context_projection(
            workspace,
            ctx_store,
            content,
            author="alex_briefing",
        )
        get_knowledge_audit_service().invalidate_agent(agent.id)
        logger.info("Project context written for %s", agent.name)
        updated += 1

    if broadcast_callback:
        await broadcast_callback({
            "type": "briefing_complete",
            "data": {"team_id": team_id, "agent_count": len(agents), "agents_updated": updated},
        })
    logger.info("Project briefing distributed to %s/%s agents in team %s", updated, len(agents), team_id)


async def run_targeted_rebriefing(agent_id: str, document_text: str, source_name: str, broadcast_callback=None) -> bool:
    """
    Update a single agent's project_context.md with content from a new document or URL.
    """
    from app.core.workspace import get_workspace_manager

    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    agent = factory.get_agent(agent_id)
    if not agent:
        logger.error(f"Agent {agent_id} not found for targeted rebriefing")
        return False

    project_ctx = ctx_store.load_context() or {}
    project_summary = _build_project_summary(project_ctx)

    wm = get_workspace_manager()
    workspace = wm.get(agent.id, agent.name, agent.title)
    factory.update_agent_occupancy(
        agent.id,
        occupancy_status=AgentOccupancyStatus.BUSY,
        occupancy_reason=AgentOccupancyReason.REBRIEFING,
        current_task_title=f"Mise à jour contexte : {source_name}",
        busy_since=_now_iso(),
    )
    await _broadcast_agent_status(agent.id, broadcast_callback)

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        new_ctx = await _generate_role_project_context(
            client=client,
            model=settings.claude_model,
            agent=agent,
            project_summary=project_summary,
            source_name=source_name,
            source_text=document_text,
        )
        _write_project_context_projection(
            workspace,
            ctx_store,
            new_ctx,
            author=f"knowledge:{source_name}",
        )
        get_knowledge_audit_service().invalidate_agent(agent.id)
        logger.info(f"project_context updated for {agent.name} from '{source_name}'")

        factory.clear_agent_occupancy(agent.id)
        await _broadcast_agent_status(agent.id, broadcast_callback)
        return True

    except Exception as e:
        logger.exception(f"Targeted rebriefing failed for {agent.name}: {e}")
        factory.clear_agent_occupancy(agent.id)
        await _broadcast_agent_status(agent.id, broadcast_callback)
        return False


async def run_document_rebriefing(doc_id: str, broadcast_callback=None):
    """
    Re-generate project_context.md for every agent across all teams,
    incorporating the content of a newly shared document.
    """
    from app.core.document_store import get_document_store
    from app.core.workspace import get_workspace_manager

    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    doc_store = get_document_store()
    meta = doc_store.get_document(doc_id)
    if not meta:
        logger.error(f"Document {doc_id} not found for rebriefing")
        return

    doc_text = doc_store.get_full_text(doc_id, max_chars=15000)
    if not doc_text:
        logger.warning(f"Document {doc_id} has no extractable text")
        return

    project_ctx = ctx_store.load_context() or {}
    project_summary = _build_project_summary(project_ctx)

    all_agents = [a for a in factory.list_agents() if a.team_id is not None]
    if not all_agents:
        logger.warning("No team agents found for rebriefing")
        return

    if broadcast_callback:
        await broadcast_callback({
            "type": "briefing_start",
            "data": {"doc_id": doc_id, "filename": meta.filename, "agent_count": len(all_agents)},
        })

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    updated = 0
    wm = get_workspace_manager()
    for agent in all_agents:
        try:
            content = await _generate_role_project_context(
                client=client,
                model=settings.claude_model,
                agent=agent,
                project_summary=project_summary,
                source_name=meta.filename,
                source_text=doc_text,
            )
        except Exception as e:
            logger.exception("Document rebriefing failed for %s: %s", agent.name, e)
            continue
        if not content:
            logger.warning("Document rebriefing returned empty content for %s", agent.name)
            continue
        workspace = wm.get(agent.id, agent.name, agent.title)
        _write_project_context_projection(
            workspace,
            ctx_store,
            content.strip(),
            author=f"doc_rebriefing:{meta.filename}",
        )
        get_knowledge_audit_service().invalidate_agent(agent.id)
        logger.info(f"project_context updated for {agent.name} from document '{meta.filename}'")
        updated += 1

    if broadcast_callback:
        await broadcast_callback({
            "type": "briefing_complete",
            "data": {"doc_id": doc_id, "filename": meta.filename, "agents_updated": updated},
        })
    logger.info(f"Document rebriefing complete: {updated}/{len(all_agents)} agents updated")


async def run_agent_research(agent_id: str, topic: str, broadcast_callback=None) -> bool:
    """
    Run an autonomous web research session for an agent using the native Anthropic runner.
    The agent searches, synthesises, and saves findings to skills/research_{slug}.md.
    """
    import re
    import os

    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    agent_cfg = factory.get_agent(agent_id)
    if not agent_cfg:
        logger.error(f"Agent {agent_id} not found for research")
        return False

    # Make SERPER_API_KEY available to SerperDevTool (reads from env)
    if has_web_search(settings):
        os.environ["SERPER_API_KEY"] = settings.serper_api_key

    slug = re.sub(r"[^\w]", "_", topic.lower())[:40]
    skill_name = f"research_{slug}"

    project_ctx = ctx_store.load_context() or {}
    project_summary = _build_project_summary(project_ctx)

    from app.core.workspace import get_workspace_manager
    wm = get_workspace_manager()
    workspace = wm.get(agent_cfg.id, agent_cfg.name, agent_cfg.title)
    current_project_ctx = workspace.read_skill("project_context") or ""

    factory.update_agent_occupancy(
        agent_id,
        occupancy_status=AgentOccupancyStatus.BUSY,
        occupancy_reason=AgentOccupancyReason.RESEARCH,
        current_task_title=f"Recherche : {topic}",
        busy_since=_now_iso(),
    )
    await _broadcast_agent_status(agent_id, broadcast_callback)

    try:
        from anthropic import AsyncAnthropic
        from app.agents.anthropic_runner import AnthropicAgentRunner
        from app.agents.base_agent import build_agent_model_name
        from app.tools.registry import get_tools_for_agent_native
        from app.models.agent import ModelTier

        native_tools = get_tools_for_agent_native(
            agent_cfg.tools,
            agent_cfg.workspace_path,
            git_bindings=agent_cfg.git_bindings,
            mcp_tool_bindings=agent_cfg.mcp_tool_bindings,
            allow_git_write=False,
        )

        research_model = build_agent_model_name(agent_cfg)
        system_prompt = (
            f"{agent_cfg.backstory}\n\n"
            f"## Project context\n{current_project_ctx[:1500]}\n\n"
            f"## Project overview\n{project_summary}"
        )
        user_message = (
            f"Research the following topic thoroughly: **{topic}**\n\n"
            f"As {agent_cfg.name} ({agent_cfg.title}), focus on what is most relevant to your role "
            f"and to the project context above.\n\n"
            f"Instructions:\n"
            f"1. Perform 3–5 targeted web searches on different angles of the topic\n"
            f"2. Browse 2–3 of the most promising result pages for deeper content\n"
            f"3. Synthesise your findings into a structured Markdown document\n"
            f"4. Save it using skill_write with skill_name='{skill_name}'\n\n"
            f"The document MUST be structured as follows:\n\n"
            f"## Summary\n"
            f"(2–3 sentence overview of what you found)\n\n"
            f"## Key Findings\n"
            f"For each finding, include:\n"
            f"- **Claim**: what you found\n"
            f"- **Source**: URL or publication name where you verified it\n"
            f"- **Confidence**: High / Medium / Low\n"
            f"- **Relevance**: why it matters for your role on this project\n\n"
            f"## Data Points\n"
            f"List only numbers and statistics found in actual sources, with explicit citations.\n"
            f"Format: `[Stat] — Source: [URL or publication], [Year if known]`\n\n"
            f"## Gaps and Open Questions\n"
            f"What you could NOT find or confirm. Flag these explicitly.\n\n"
            f"## Actionable Insights\n"
            f"What this research means for your specific role and tasks.\n\n"
            f"CRITICAL: Do NOT invent numbers. If you cannot find a verified source for a statistic, "
            f"put it in Gaps. A gap acknowledged is far better than a fabricated figure."
        )

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        runner = AnthropicAgentRunner(client=client)
        _result_text, inp_tokens, out_tokens = await runner.run(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=native_tools,
            model=research_model,
            max_tokens=agent_cfg.max_tokens,
            max_iter=10,
        )
        get_usage_tracker().log(research_model, inp_tokens, out_tokens)

        logger.info(f"Research complete for {agent_cfg.name}: topic='{topic}', skill='{skill_name}'")
        get_knowledge_audit_service().invalidate_agent(agent_id)
        factory.clear_agent_occupancy(agent_id)
        await _broadcast_agent_status(agent_id, broadcast_callback)
        if broadcast_callback:
            await broadcast_callback({
                "type": "research_complete",
                "data": {"agent_id": agent_id, "topic": topic, "skill_name": skill_name},
            })
        return True

    except Exception as e:
        logger.exception(f"Research failed for {agent_cfg.name}: {e}")
        factory.clear_agent_occupancy(agent_id)
        await _broadcast_agent_status(agent_id, broadcast_callback)
        return False


async def run_learning_phase_for_team(team_id: str, broadcast_callback=None):
    factory = get_agent_factory()
    agents = factory.get_team_agents(team_id)
    tasks = [run_learning_phase(agent, broadcast_callback) for agent in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(f"Learning phase complete for team {team_id}: {results}")

    # After learning, run a project briefing to write role-specific project_context.md
    # based on the full project context — overrides the self-generated version from learning
    try:
        await run_project_briefing(team_id, broadcast_callback)
    except Exception as e:
        logger.warning(f"Post-learning project briefing failed for team {team_id}: {e}")
