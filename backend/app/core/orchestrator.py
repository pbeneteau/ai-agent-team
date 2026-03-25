"""
Hybrid task orchestrator.
Builds an explicit execution plan, runs independent nodes in parallel, and only
shares context when dependencies explicitly require it.
"""
import asyncio
import json
import logging
import os
import shutil
import threading
import traceback
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Optional

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from app.agents.anthropic_runner import AgentMaxIterError, AnthropicAgentRunner
from app.config import get_settings, has_web_search
from app.config.prompts import (
    EVIDENCE_RULES_SUFFIX,
    PLANNER_SCHEMA_HINT,
    PLANNER_SYSTEM_PROMPT,
    PLANNER_USER_PROMPT,
    RESEARCH_MANDATE_SUFFIX,
    RESULT_METADATA_PROMPT,
    RESULT_METADATA_SCHEMA_HINT,
    SELF_AUGMENT_SUFFIX,
    SMART_SKILLS_SELECT_PROMPT,
)
from app.config.token_budgets import (
    ORCHESTRATOR_DEPENDENCY_RESULT_BUDGET,
    ORCHESTRATOR_DEPENDENCY_SUMMARY_MAX_TOKENS,
    ORCHESTRATOR_DEPENDENCY_SUMMARY_TARGET_CHARS,
    ORCHESTRATOR_DEPENDENCY_SUMMARY_THRESHOLD,
    ORCHESTRATOR_MEMORY_CTX_BUDGET,
    ORCHESTRATOR_MEMORY_EPISODES_BUDGET,
    ORCHESTRATOR_MEMORY_RESEARCH_BUDGET,
    ORCHESTRATOR_MEMORY_SKILLS_BUDGET,
    ORCHESTRATOR_MEMORY_TEAM_KNOWLEDGE_BUDGET,
    ORCHESTRATOR_MEMORY_WORK_LEARNINGS_BUDGET,
    ORCHESTRATOR_PLANNER_MAX_TOKENS,
    ORCHESTRATOR_PLANNER_REPAIR_MAX_TOKENS,
    ORCHESTRATOR_RESULT_METADATA_MAX_TOKENS,
    ORCHESTRATOR_RESULT_METADATA_REPAIR_MAX_TOKENS,
    ORCHESTRATOR_TASK_CONTEXT_DOCS_BUDGET,
    ORCHESTRATOR_TASK_CONTEXT_PROJECT_BUDGET,
    SMART_SKILLS_SELECT_MAX_TOKENS,
    SMART_SKILLS_SELECT_THRESHOLD,
    VECTOR_RETRIEVAL_TOP_K,
)
from app.core.agent_factory import get_agent_factory
from app.core.document_store import DocumentStore, get_document_store
from app.core.learning import run_learn_from_work, write_episode
from app.core.project_brief import render_project_brief_summary
from app.core.structured_json import StructuredJsonError, request_structured_json_async
from app.core.usage_tracker import get_usage_tracker, _cost_usd as _tracker_cost_usd
from app.core.workspace import get_workspace_manager
from app.memory.project_context import get_project_context_store
from app.memory.skills_store import get_skills_store
from app.models.agent import (
    AgentConfig,
    AgentOccupancyReason,
    AgentOccupancyStatus,
    AgentRole,
    AgentStatus,
    ModelTier,
    build_agent_status_payload,
)
from app.models.task import (
    TaskDeliverable,
    TaskExecutionEligibility,
    TaskExecutionMode,
    TaskExecutionNode,
    TaskExecutionPlan,
    TaskNodeStatus,
    TaskNodeType,
    TaskPlanStatus,
    TaskPriority,
    TaskProgressEntry,
    TaskResponse,
    TaskStatus,
)
from app.models.task_comment import CommentAuthorType, CommentType, TaskCommentCreate
from app.models.team import TeamConfig
from app.tools.registry import get_tools_for_agent_native
from app.tools.spec import ToolSpec

logger = logging.getLogger(__name__)


def _get_cached_readiness_score(agent_id: str) -> Optional[int]:
    """Return the agent's cached readiness score (0-100) without triggering LLM computation.

    Returns None if no cache is available yet.
    """
    try:
        settings = get_settings()
        cache_path = Path(settings.data_dir) / "knowledge_readiness" / f"agent-{agent_id}.json"
        if not cache_path.exists():
            return None
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        score = data.get("readiness_score")
        if isinstance(score, int):
            return score
        return None
    except Exception:
        return None

BroadcastCallback = Callable[[dict], Awaitable[None]]


@dataclass(slots=True)
class _FailureDetails:
    error: str
    error_type: str
    error_traceback: Optional[str]
    failure_stage: Optional[str]


@dataclass(slots=True)
class _WaveNodeFailure:
    node: TaskExecutionNode
    agent: AgentConfig
    details: _FailureDetails
    cause: Exception


class _TaskExecutionFailure(RuntimeError):
    def __init__(
        self,
        error: str,
        *,
        error_type: str,
        error_traceback: Optional[str],
        failure_stage: Optional[str],
    ):
        super().__init__(error)
        self.error = error
        self.error_type = error_type
        self.error_traceback = error_traceback
        self.failure_stage = failure_stage


def _format_failure_message(error_type: str, message: str) -> str:
    clean_message = (message or "").strip()
    if not clean_message:
        return error_type
    if clean_message.startswith(f"{error_type}:"):
        return clean_message
    return f"{error_type}: {clean_message}"


def _capture_failure_details(
    exc: Exception,
    *,
    failure_stage: Optional[str] = None,
    error: Optional[str] = None,
    error_traceback: Optional[str] = None,
) -> _FailureDetails:
    if isinstance(exc, _TaskExecutionFailure):
        return _FailureDetails(
            error=error or exc.error,
            error_type=exc.error_type,
            error_traceback=error_traceback if error_traceback is not None else exc.error_traceback,
            failure_stage=exc.failure_stage or failure_stage,
        )

    error_type = type(exc).__name__
    summary = error or _format_failure_message(error_type, str(exc))
    trace = error_traceback
    if trace is None and exc.__traceback__ is not None:
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    return _FailureDetails(
        error=summary,
        error_type=error_type,
        error_traceback=trace,
        failure_stage=failure_stage,
    )


def _apply_failure_details(target: TaskResponse | TaskExecutionNode, details: _FailureDetails):
    target.error = details.error
    target.error_type = details.error_type
    target.error_traceback = details.error_traceback
    target.failure_stage = details.failure_stage


def _clear_failure_details(target: TaskResponse | TaskExecutionNode):
    target.error = None
    target.error_type = None
    target.error_traceback = None
    target.failure_stage = None


def _build_wave_failure(failures: list[_WaveNodeFailure]) -> _TaskExecutionFailure:
    if len(failures) == 1:
        failure = failures[0]
        return _TaskExecutionFailure(
            f"{failure.agent.name} / {failure.node.title}: {failure.details.error}",
            error_type=failure.details.error_type,
            error_traceback=failure.details.error_traceback,
            failure_stage=failure.details.failure_stage,
        )

    summary_lines = [
        (
            f"- {failure.agent.name} / {failure.node.title} "
            f"[{failure.details.error_type}{f' @ {failure.details.failure_stage}' if failure.details.failure_stage else ''}] "
            f"{failure.details.error}"
        )
        for failure in failures
    ]
    traceback_sections = [
        "\n".join(
            part
            for part in [
                f"## {failure.agent.name} / {failure.node.title}",
                f"error_type: {failure.details.error_type}",
                f"failure_stage: {failure.details.failure_stage or 'unknown'}",
                failure.details.error_traceback or failure.details.error,
            ]
            if part
        )
        for failure in failures
    ]
    return _TaskExecutionFailure(
        "Multiple execution nodes failed:\n" + "\n".join(summary_lines),
        error_type="MultipleNodeFailures",
        error_traceback="\n\n".join(traceback_sections),
        failure_stage="node_execution_wave",
    )

_EXTERNAL_FACT_KEYWORDS = {
    "market", "marché", "competitor", "concurren", "benchmark", "statistic",
    "industri", "research", "funding", "investor", "levée", "fundrais",
    "pricing", "revenue", "revenu", "chiffre", "regulation", "compliance",
    "trend", "tendance", "growth", "croissance", "tam", "sam", "som",
    "size", "taille", "percent", "pourcent", "survey", "étude", "report",
    "analyse", "analysis", "data", "donnée", "source", "citation",
    "evidence", "preuve", "validation", "stratégie", "strategy",
    "business plan", "financial", "financier", "model", "modèle",
}

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _classify_task(description: str) -> str:
    desc_lower = description.lower()
    pure_internal_signals = [
        "refactor", "fix bug", "corriger", "modifier le code", "edit file",
        "rename", "renommer", "format", "lint", "test unitaire", "unit test",
        "dockerfile", "deploy script", "migration sql",
    ]
    is_pure_internal = any(sig in desc_lower for sig in pure_internal_signals)
    has_external_keyword = any(kw in desc_lower for kw in _EXTERNAL_FACT_KEYWORDS)
    if is_pure_internal and not has_external_keyword:
        return "pure_internal"
    return "external_fact_task"


def _project_context_summary(ctx: dict[str, Any]) -> str:
    return render_project_brief_summary(
        ctx,
        include_meta=True,
        description_limit=ORCHESTRATOR_TASK_CONTEXT_PROJECT_BUDGET,
        notes_limit=600,
    )


class _PlannerNodePayload(BaseModel):
    agent_id: str
    title: str
    brief: str
    depends_on: list[str] = Field(default_factory=list)


class _PlannerPayload(BaseModel):
    mode: Literal["standalone", "dependency_graph"]
    planning_notes: str
    nodes: list[_PlannerNodePayload] = Field(default_factory=list)


class _TaskResultMetadataPayload(BaseModel):
    sources: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


async def _smart_select_skills(core_skills: str, task_context: str, budget: int) -> Optional[str]:
    """INTERIM: Use a lightweight Haiku call to select relevant core_skills sections.
    Will be replaced by ARCH-1 vector retrieval."""
    settings = get_settings()
    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.claude_model_haiku,
            max_tokens=SMART_SKILLS_SELECT_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": SMART_SKILLS_SELECT_PROMPT.format(
                    task_context=task_context[:800],
                    core_skills=core_skills,
                    budget=budget,
                ),
            }],
        )
        from app.core.usage_tracker import get_usage_tracker
        get_usage_tracker().log(settings.claude_model_haiku, response.usage.input_tokens, response.usage.output_tokens)
        result = response.content[0].text.strip()
        return result if result and len(result) > 50 else None
    except Exception as exc:
        logger.debug("Smart skills selection failed, falling back to truncation: %s", exc)
        return None


async def _build_agent_memory_pack(cfg: AgentConfig, skills_store, *, task_context: str = "") -> str:
    """
    Persistent memory owned by the agent.
    This excludes shared runtime context and task-specific document injection.
    """
    parts: list[str] = []

    try:
        workspace = get_workspace_manager().get(cfg.id, cfg.name, cfg.title)
        project_ctx = workspace.read_skill("project_context")
        if project_ctx:
            parts.append(
                f"## Your role-specific brief projection\n{_truncate(project_ctx, ORCHESTRATOR_MEMORY_CTX_BUDGET)}"
            )

        work_learnings = workspace.read_skill("work_learnings")
        if work_learnings:
            parts.append(
                f"## Your reusable work learnings\n{_truncate(work_learnings, ORCHESTRATOR_MEMORY_WORK_LEARNINGS_BUDGET)}"
            )

        # Episodic memory — agent's task history
        episodes = workspace.read_skill("episodes")
        if episodes:
            parts.append(
                f"## Your task history\n{_truncate(episodes, ORCHESTRATOR_MEMORY_EPISODES_BUDGET)}"
            )

        # Team knowledge — shared learnings validated by multiple team members
        if cfg.team_id:
            shared_ws = get_workspace_manager().shared
            team_knowledge = shared_ws.read_skill(f"team_knowledge_{cfg.team_id}")
            if team_knowledge:
                parts.append(
                    f"## Shared team knowledge\n{_truncate(team_knowledge, ORCHESTRATOR_MEMORY_TEAM_KNOWLEDGE_BUDGET)}"
                )

        # ARCH-1: Vector retrieval for core_skills + research (task-dependent memory)
        # Falls back to direct injection if ChromaDB is unavailable or has no indexed data
        vector_retrieved = False
        if task_context:
            try:
                from app.memory.vector_store import get_vector_store
                vs = get_vector_store()
                collection_name = f"agent_skills_{cfg.id}"
                results = vs.query(collection_name, [task_context[:500]], n_results=VECTOR_RETRIEVAL_TOP_K)
                if results:
                    chunks = "\n\n".join(r["document"] for r in results)
                    combined_budget = ORCHESTRATOR_MEMORY_SKILLS_BUDGET + ORCHESTRATOR_MEMORY_RESEARCH_BUDGET
                    parts.append(
                        f"## Relevant expertise for this task\n{_truncate(chunks, combined_budget)}"
                    )
                    vector_retrieved = True
            except Exception as vec_exc:
                logger.debug("Vector retrieval failed for %s, falling back to direct injection: %s", cfg.id, vec_exc)

        if not vector_retrieved:
            # Fallback: direct injection with positional truncation
            research_files = sorted(
                workspace.skills.glob("research_*.md"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            research_parts: list[str] = []
            research_used = 0
            for research_file in research_files:
                content = research_file.read_text(encoding="utf-8")
                remaining = ORCHESTRATOR_MEMORY_RESEARCH_BUDGET - research_used
                if remaining <= 0:
                    break
                clipped = _truncate(content, remaining)
                if clipped:
                    research_parts.append(f"### {research_file.stem}\n{clipped}")
                    research_used += len(clipped)
            if research_parts:
                parts.append("## Your research notes\n" + "\n\n".join(research_parts))

            core_skills = workspace.read_skill("core_skills")
            if core_skills:
                # Use smart selection via Haiku if core_skills exceeds threshold
                if len(core_skills) > SMART_SKILLS_SELECT_THRESHOLD and task_context:
                    selected = await _smart_select_skills(core_skills, task_context, ORCHESTRATOR_MEMORY_SKILLS_BUDGET)
                    if selected:
                        core_skills = selected
                parts.append(
                    f"## Your methodology and expertise\n{_truncate(core_skills, ORCHESTRATOR_MEMORY_SKILLS_BUDGET)}"
                )
    except Exception:
        fallback_ctx = skills_store.read_skill(cfg.id, "project_context")
        if fallback_ctx:
            parts.append(
                f"## Your role-specific brief projection\n{_truncate(fallback_ctx, ORCHESTRATOR_MEMORY_CTX_BUDGET)}"
            )

    return "\n\n---\n\n".join(parts)


_AUTO_ASSUME_SUFFIX = """

CRITICAL RULE — AUTO-ASSUME:
If you encounter missing information, ambiguity, or a situation where you would
normally ask the user for clarification, you MUST NOT stop or ask. Instead:
1. Make the safest reasonable assumption.
2. Clearly document the assumption inline using this exact format:
   [⚠️ ASSUMPTION MADE: <what you assumed and why>]
3. Continue working and finish the deliverable.
You are autonomous. Never pause for human input."""


async def _enrich_backstory(cfg: AgentConfig, skills_store, *, task_context: str = "") -> str:
    parts = [cfg.backstory]
    memory_pack = await _build_agent_memory_pack(cfg, skills_store, task_context=task_context)
    if memory_pack:
        parts.append(f"\n\n## Your persistent memory\n{memory_pack}")
    if cfg.workspace_path:
        parts.append(
            f"\n\n## Your workspace\n"
            f"Directory: `{cfg.workspace_path}`\n"
            f"Use `workspace_list` to browse, `workspace_shell` to run commands, `git_clone` to clone repos."
        )
    parts.append(_AUTO_ASSUME_SUFFIX)
    return "".join(parts)


def _format_explicit_documents_context(doc_store: DocumentStore, document_ids: list[str]) -> str:
    if not document_ids:
        return ""

    parts: list[str] = []
    used = 0
    for doc_id in document_ids:
        meta = doc_store.get_document(doc_id)
        if not meta:
            continue
        remaining = ORCHESTRATOR_TASK_CONTEXT_DOCS_BUDGET - used
        if remaining <= 0:
            break
        text = doc_store.get_full_text(doc_id, max_chars=remaining)
        if not text:
            continue
        header = f"### {meta.filename}"
        if meta.description:
            header += f"\nDescription: {meta.description}"
        entry = f"{header}\n{text}"
        clipped = _truncate(entry, remaining)
        parts.append(clipped)
        used += len(clipped)

    if not parts:
        return ""

    return "## Explicit task documents\n" + "\n\n".join(parts)


def _build_task_context_pack(task: TaskResponse, team: Optional[TeamConfig], ctx_store, doc_store: DocumentStore) -> str:
    ctx = ctx_store.load_context() or {}
    parts = [_project_context_summary(ctx)]

    if team:
        team_parts = [
            f"Team: {team.name}",
            f"Team description: {team.description}",
        ]
        if team.scope_note:
            team_parts.append(f"Current team scope: {team.scope_note}")
        if team.domain:
            team_parts.append(f"Team domain: {team.domain}")
        parts.append("## Team context\n" + "\n".join(team_parts))

    docs_context = _format_explicit_documents_context(doc_store, task.context_document_ids)
    if docs_context:
        parts.append(docs_context)

    return "\n\n---\n\n".join(part for part in parts if part)


def _compute_quality_gate(
    result_text: str,
    sources: list[str],
    assumptions: list[str],
    warnings: list[str],
) -> tuple[int, list[str]]:
    """Rule-based quality score (0-100) and flags — no LLM call."""
    import re

    score = 60
    flags: list[str] = []

    # --- Sources bonus / malus ---
    url_sources = [s for s in sources if s.startswith("http")]
    if len(url_sources) >= 1:
        score += min(15 + 5 * (len(url_sources) - 1), 25)
    elif not sources and not re.findall(r"https?://\S+", result_text):
        score -= 20
        flags.append("Aucune source vérifiable trouvée")

    # --- Assumptions penalty ---
    n_assumptions = len(assumptions)
    if n_assumptions:
        score -= min(n_assumptions * 5, 15)
        flags.append(f"{n_assumptions} hypothèse(s) non résolue(s)")

    # --- Warnings penalty ---
    n_warnings = len(warnings)
    if n_warnings:
        score -= min(n_warnings * 5, 15)
        flags.append(f"{n_warnings} point(s) non vérifiés")

    # --- TBD/TODO in text ---
    tbd_count = len(re.findall(r"\b(?:TBD|TODO|À confirmer)\b", result_text, re.IGNORECASE))
    if tbd_count:
        score -= min(tbd_count * 3, 15)
        flags.append(f"{tbd_count} TBD non résolus dans le texte")

    # --- Length checks ---
    if len(result_text) < 50:
        score -= 40
        flags.append("Résultat vide ou insuffisant")
    elif len(result_text) < 200:
        score -= 20
        flags.append("Résultat trop court")

    score = max(0, min(100, score))
    return score, flags


def _dependency_context(plan: TaskExecutionPlan, node: TaskExecutionNode) -> str:
    """Synchronous version — used by tests and callers that cannot await."""
    if not node.depends_on:
        return ""

    parts: list[str] = []
    nodes_by_id = {plan_node.id: plan_node for plan_node in plan.nodes}
    for dependency_id in node.depends_on:
        dependency = nodes_by_id.get(dependency_id)
        if not dependency or not dependency.result:
            continue
        title = dependency.title or dependency.assigned_agent_name or dependency.id
        parts.append(
            f"### Dependency: {title}\n"
            f"Agent: {dependency.assigned_agent_name or dependency.assigned_agent_id or 'Unknown'}\n"
            f"{_truncate(dependency.result, ORCHESTRATOR_DEPENDENCY_RESULT_BUDGET)}"
        )
    if not parts:
        return ""
    return "## Upstream results you are allowed to use\n" + "\n\n".join(parts)


async def _smart_summarize(
    text: str,
    *,
    budget: int,
    target_chars: int,
    client: AsyncAnthropic,
    model: str,
    context_label: str = "",
) -> str:
    """Return text as-is if it fits within budget.

    When text exceeds budget, call Claude to produce an intelligent summary
    preserving conclusions, sources, and warnings — instead of hard-truncating.
    Falls back to brute truncation if the API call fails.
    """
    if len(text) <= budget:
        return text
    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=ORCHESTRATOR_DEPENDENCY_SUMMARY_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": (
                    f"Summarise the following specialist agent output to under {target_chars} characters.\n"
                    "Preserve: all conclusions, all cited sources/URLs, all verified data points, "
                    "all warnings, assumptions, and TBDs.\n"
                    "Compress: prose, repetition, scaffolding, and intermediate reasoning steps.\n"
                    "Return only the summary — no preamble, no explanation.\n\n"
                    f"---\n{text[:20_000]}\n---"
                ),
            }],
        )
        get_usage_tracker().log(model, resp.usage.input_tokens, resp.usage.output_tokens)
        summary = resp.content[0].text.strip()
        logger.debug(
            "_smart_summarize %s: %d → %d chars", context_label, len(text), len(summary)
        )
        return summary
    except Exception as exc:
        logger.warning(
            "_smart_summarize failed for '%s', falling back to truncation: %s", context_label, exc
        )
        return _truncate(text, budget)


async def _async_dependency_context(
    plan: TaskExecutionPlan,
    node: TaskExecutionNode,
    client: AsyncAnthropic,
    model: str,
) -> str:
    """Async version of _dependency_context that summarizes long results intelligently."""
    if not node.depends_on:
        return ""

    nodes_by_id = {plan_node.id: plan_node for plan_node in plan.nodes}
    parts: list[str] = []
    for dependency_id in node.depends_on:
        dependency = nodes_by_id.get(dependency_id)
        if not dependency or not dependency.result:
            continue
        title = dependency.title or dependency.assigned_agent_name or dependency.id
        summarized = await _smart_summarize(
            dependency.result,
            budget=ORCHESTRATOR_DEPENDENCY_SUMMARY_THRESHOLD,
            target_chars=ORCHESTRATOR_DEPENDENCY_SUMMARY_TARGET_CHARS,
            client=client,
            model=model,
            context_label=title,
        )
        parts.append(
            f"### Dependency: {title}\n"
            f"Agent: {dependency.assigned_agent_name or dependency.assigned_agent_id or 'Unknown'}\n"
            f"{summarized}"
        )
    if not parts:
        return ""
    return "## Upstream results you are allowed to use\n" + "\n\n".join(parts)


def _expected_output_for_node(node: TaskExecutionNode, requires_external_research: bool) -> str:
    if node.node_type == TaskNodeType.LEAD_COMPILE:
        return (
            "A complete, well-structured deliverable that integrates all specialist outputs. "
            "You MUST read the full specialist files using task_deliverable_list then task_deliverable_read "
            "before synthesising — do not compile from truncated context alone. "
            "Include a consolidated ## Sources section and a ## Warnings & Assumptions section."
        )

    if requires_external_research:
        return (
            "A focused, evidence-based contribution with explicit web research. "
            "MUST include a ## Sources section and a ## Unverified / TBD section."
        )

    return (
        "A focused, structured contribution relevant to your specialization. "
        "Include a ## Sources section for references used and a ## Unverified / TBD section."
    )


def _prompt_for_node(
    task: TaskResponse,
    node: TaskExecutionNode,
    cfg: AgentConfig,
    task_context_pack: str,
    dependency_context_text: str,
    requires_external_research: bool,
) -> str:
    task_suffix = EVIDENCE_RULES_SUFFIX + SELF_AUGMENT_SUFFIX
    if requires_external_research and node.node_type != TaskNodeType.LEAD_COMPILE:
        task_suffix = RESEARCH_MANDATE_SUFFIX + task_suffix

    base_sections = [
        f"You are {cfg.name} ({cfg.title}).",
        f"Your specialization: {cfg.specialization}",
        "",
        f"Root task title: {task.title}",
        "Root task description:",
        task.description,
        "",
        f"Task deliverables directory: data/task_deliverables/{task.id}",
        "To inspect existing task deliverables, use task_deliverable_list and then task_deliverable_read with a relative path.",
        "If your work should exist as one or more concrete files attached to this task, write them with task_deliverable_write.",
        "Use file_write only for scratch files, repo edits, or intermediate workspace artifacts that should stay private to your workspace.",
        "Do not use file_read on data/task_deliverables/... paths. file_read is scoped to your private workspace, not the shared task deliverables directory.",
        "Do not use file_write for final task deliverables that the user should review from the task detail page.",
        "IMPORTANT: task_deliverable_write requires BOTH arguments every time: `path` and the FULL file `content`.",
        "IMPORTANT: task_deliverable_read requires a relative file path such as authored/summary.md, not a directory path.",
        "NEVER call task_deliverable_write with only a path.",
        "NEVER create placeholder, empty, or stub deliverables.",
        "First draft the full file content in your reasoning, then call task_deliverable_write exactly once with both `path` and `content`.",
        "Never call task_deliverable_write with only a path. Draft the full file content first, then write it in one call.",
        "Store agent-authored files under authored/ (for example authored/summary.md or authored/slides/outline.md).",
        "Invalid example: task_deliverable_write(path='authored/summary.md')",
        "Valid example: task_deliverable_write(path='authored/summary.md', content='# Summary\\n\\nActual content here')",
        "",
        "Your subtask:",
        node.description,
    ]

    if task_context_pack:
        base_sections.extend(["", task_context_pack])

    if dependency_context_text:
        base_sections.extend(["", dependency_context_text])

    if node.node_type == TaskNodeType.LEAD_COMPILE:
        base_sections.extend([
            "",
            "You are compiling the final deliverable.",
            "IMPORTANT: The upstream dependency outputs shown above may be truncated summaries.",
            "Before compiling, use task_deliverable_list to discover all files written by the specialist agents,",
            "then use task_deliverable_read to read each specialist's full authored file (e.g. authored/report.md).",
            "Do not rely solely on the truncated context injected above — always read the full outputs first.",
            "Preserve citations, consolidate sources, and clearly separate verified information from assumptions or TBDs.",
        ])
    else:
        base_sections.extend([
            "",
            "Stay strictly inside your scope.",
            "Do not solve the whole project. Deliver only the part that belongs to your expertise.",
            "Do not assume you have access to any other specialist's work unless it appears in the allowed dependency results section.",
        ])

    prompt = "\n".join(base_sections) + task_suffix

    if node.additional_instructions:
        prompt += (
            "\n\n## Additional instructions from the operator\n"
            + node.additional_instructions
        )

    return prompt


def _build_task_deliverable_write_tool(task_root: Path) -> ToolSpec:
    root = task_root.resolve()

    def task_deliverable_write(path: str, content: str) -> str:
        relative = (path or "").strip().lstrip("/")
        if not relative:
            return "ERROR: path is required"
        if not (content or "").strip():
            return "ERROR: content is required. Provide both `path` and full file `content`."
        target = (root / relative).resolve()
        if not str(target).startswith(str(root)):
            return "ERROR: path outside task deliverables directory"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
        return f"Saved deliverable: {target.relative_to(root)}"

    return ToolSpec(
        name="task_deliverable_write",
        description=(
            "Write a deliverable file inside the current task folder. "
            "Use relative paths only, preferably under authored/ (e.g. authored/summary.md). "
            "IMPORTANT: always provide both `path` and the full file `content` in every call. "
            "Never call this tool with only a path."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path such as 'authored/summary.md'",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content to save",
                },
            },
            "required": ["path", "content"],
        },
        executor=task_deliverable_write,
    )


def _build_task_deliverable_list_tool(task_root: Path) -> ToolSpec:
    root = task_root.resolve()

    def task_deliverable_list(sub_path: str = ".") -> str:
        relative = (sub_path or ".").strip()
        target = (root / relative).resolve()
        if not str(target).startswith(str(root)):
            return "ERROR: path outside task deliverables directory"
        if not target.exists():
            return "No files yet."
        if target.is_file():
            return str(target.relative_to(root))
        entries = []
        for item in sorted(target.iterdir()):
            label = str(item.relative_to(root))
            if item.is_dir():
                label += "/"
            entries.append(label)
        return "\n".join(entries) if entries else "No files yet."

    return ToolSpec(
        name="task_deliverable_list",
        description="List files already present inside the current task deliverables folder.",
        input_schema={
            "type": "object",
            "properties": {
                "sub_path": {
                    "type": "string",
                    "description": "Optional relative folder to inspect (default: '.')",
                }
            },
            "required": [],
        },
        executor=task_deliverable_list,
    )


def _build_task_deliverable_read_tool(task_root: Path) -> ToolSpec:
    root = task_root.resolve()

    def task_deliverable_read(path: str) -> str:
        relative = (path or "").strip().lstrip("/")
        if not relative:
            return "ERROR: path is required"
        target = (root / relative).resolve()
        if not str(target).startswith(str(root)):
            return "ERROR: path outside task deliverables directory"
        if not target.exists():
            return f"ERROR: deliverable not found: {relative}"
        if not target.is_file():
            return f"ERROR: not a file: {relative}. Use task_deliverable_list to inspect directories."
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"ERROR: deliverable is not valid UTF-8 text: {relative}"
        except Exception as exc:
            return f"ERROR: unable to read deliverable {relative}: {exc}"

    return ToolSpec(
        name="task_deliverable_read",
        description=(
            "Read a UTF-8 text deliverable file from the current task folder. "
            "Requires a relative file path such as 'authored/summary.md', not a directory path."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative file path such as 'authored/summary.md'",
                }
            },
            "required": ["path"],
        },
        executor=task_deliverable_read,
    )


class Orchestrator:
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_file = self.data_dir / "tasks.json"
        self.task_deliverables_dir = self.data_dir / "task_deliverables"
        self.task_deliverables_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, TaskResponse] = {}
        self._task_identifier_counter: int = 0
        self._save_lock = threading.Lock()
        self._load_tasks()

    # Migrate legacy statuses to the new 3-state model
    _STATUS_MIGRATION: dict[str, str] = {
        "pending": "drafting",
        "running": "drafting",
        "executing": "drafting",
        "completed": "approved",
        "done": "approved",
        "failed": "in_review",
        "review": "in_review",
        "triage": "drafting",
        "backlog": "drafting",
        "queued": "drafting",
        "planning": "drafting",
        "input_needed": "drafting",
        "partial": "in_review",
    }

    # Valid status transitions (simplified 3-state + cancelled)
    _VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
        TaskStatus.DRAFTING: {TaskStatus.IN_REVIEW, TaskStatus.CANCELLED},
        TaskStatus.IN_REVIEW: {TaskStatus.APPROVED, TaskStatus.DRAFTING, TaskStatus.CANCELLED},
        TaskStatus.APPROVED: set(),
        TaskStatus.CANCELLED: {TaskStatus.DRAFTING},
    }

    def _load_tasks(self):
        if self.tasks_file.exists():
            raw = json.loads(self.tasks_file.read_text(encoding="utf-8"))
            # Pre-process: migrate legacy status values before Pydantic validation
            for value in raw.values():
                if isinstance(value, dict) and value.get("status") in self._STATUS_MIGRATION:
                    value["status"] = self._STATUS_MIGRATION[value["status"]]
            self._tasks = {key: TaskResponse.model_validate(value) for key, value in raw.items()}

        # Ensure identifiers exist
        migrated = False
        for task in self._tasks.values():
            if not task.identifier:
                self._task_identifier_counter += 1
                task.identifier = f"TASK-{self._task_identifier_counter}"
                migrated = True

        # Compute identifier counter from existing tasks
        for task in self._tasks.values():
            if task.identifier and "-" in task.identifier:
                try:
                    num = int(task.identifier.split("-")[1])
                    self._task_identifier_counter = max(self._task_identifier_counter, num)
                except ValueError:
                    pass

        if migrated:
            self._save_tasks()

        for task in self._tasks.values():
            self._refresh_task_deliverables(task)

    def reconcile_interrupted_tasks(self) -> dict[str, int]:
        """
        Recover task persistence after an unclean local shutdown.

        If the backend process was killed, no task is still executing after
        restart. Running tasks must therefore be marked as interrupted.
        """
        recovered_tasks = 0
        recovered_nodes = 0
        interruption_message = "Interrupted because the local server stopped during execution."
        interruption_details = _FailureDetails(
            error=interruption_message,
            error_type="InterruptedExecution",
            error_traceback=None,
            failure_stage="runtime_recovery",
        )

        for task in self._tasks.values():
            if task.status != TaskStatus.DRAFTING:
                continue

            recovered_tasks += 1
            task.status = TaskStatus.IN_REVIEW
            _apply_failure_details(task, interruption_details)
            task.updated_at = _now_iso()

            if task.execution_plan.status in {
                TaskPlanStatus.PLANNING,
                TaskPlanStatus.READY,
                TaskPlanStatus.RUNNING,
            }:
                task.execution_plan.status = TaskPlanStatus.FAILED

            for node in task.execution_plan.nodes:
                if node.status == TaskNodeStatus.RUNNING:
                    node.status = TaskNodeStatus.FAILED
                    _apply_failure_details(node, interruption_details)
                    node.completed_at = _now_iso()
                    recovered_nodes += 1
                elif node.status in {
                    TaskNodeStatus.PENDING,
                    TaskNodeStatus.BLOCKED,
                    TaskNodeStatus.READY,
                }:
                    node.status = TaskNodeStatus.SKIPPED
                    _apply_failure_details(node, interruption_details)
                    node.completed_at = _now_iso()
                    recovered_nodes += 1

            task.progress_log.append(
                TaskProgressEntry(
                    timestamp=_now_iso(),
                    message=interruption_message,
                    stage="task_recovered_after_restart",
                )
            )
            self._sync_task_deliverables(task)

        if recovered_tasks:
            self._save_tasks()

        return {
            "recovered_tasks": recovered_tasks,
            "recovered_nodes": recovered_nodes,
        }

    def _save_tasks(self):
        with self._save_lock:
            self.tasks_file.write_text(
                json.dumps({key: value.model_dump() for key, value in self._tasks.items()}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _task_deliverables_root(self, task_id: str, *, create: bool = True) -> Path:
        root = self.task_deliverables_dir / task_id
        if create:
            root.mkdir(parents=True, exist_ok=True)
        return root

    def _task_system_deliverables_root(self, task_id: str, *, create: bool = True) -> Path:
        root = self._task_deliverables_root(task_id, create=create) / "system"
        if create:
            root.mkdir(parents=True, exist_ok=True)
        return root

    def _sanitize_filename(self, value: str, fallback: str = "deliverable") -> str:
        cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
        cleaned = "-".join(part for part in cleaned.split("-") if part)
        return (cleaned[:80] or fallback).strip("-") or fallback

    def _list_deliverable_entries(self, task_id: str) -> list[TaskDeliverable]:
        root = self._task_deliverables_root(task_id, create=False)
        if not root.exists():
            return []

        entries: list[TaskDeliverable] = []
        for item in sorted(root.rglob("*")):
            if not item.is_file():
                continue
            entries.append(
                TaskDeliverable(
                    path=str(item.relative_to(root)),
                    name=item.name,
                    type=item.suffix.lstrip(".") or "file",
                    size_bytes=item.stat().st_size,
                    modified_at=datetime.fromtimestamp(item.stat().st_mtime, UTC).isoformat(),
                )
            )
        return entries

    def _refresh_task_deliverables(self, task: TaskResponse):
        root = self._task_deliverables_root(task.id, create=False)
        task.deliverables_dir = str(Path("task_deliverables") / task.id)
        task.deliverables = self._list_deliverable_entries(task.id) if root.exists() else []

    def _render_task_deliverable(self, task: TaskResponse) -> str:
        return (
            f"# {task.title}\n\n"
            f"- Statut: {task.status.value}\n"
            f"- Priorité: {task.priority.value}\n"
            f"- Mis à jour: {task.updated_at}\n\n"
            "## Description\n\n"
            f"{task.description}\n\n"
            "## Résultat final\n\n"
            f"{task.result or 'Aucun résultat final disponible.'}\n"
        )

    def _render_node_deliverable(self, node: TaskExecutionNode) -> str:
        agent_label = node.assigned_agent_name or node.assigned_agent_id or "Agent inconnu"
        metadata = [
            f"- Statut: {node.status.value}",
            f"- Type: {node.node_type.value}",
            f"- Agent: {agent_label}",
        ]
        if node.started_at:
            metadata.append(f"- Démarré: {node.started_at}")
        if node.completed_at:
            metadata.append(f"- Terminé: {node.completed_at}")
        if node.error_type:
            metadata.append(f"- Type d'erreur: {node.error_type}")
        if node.failure_stage:
            metadata.append(f"- Stade d'échec: {node.failure_stage}")

        sections = [
            f"# {node.title}",
            "",
            *metadata,
            "",
            "## Description",
            "",
            node.description,
            "",
            "## Résultat",
            "",
            node.result or "Aucun résultat disponible.",
        ]

        if node.sources:
            sections.extend(["", "## Sources", "", *[f"- {source}" for source in node.sources]])
        if node.warnings:
            sections.extend(["", "## Warnings", "", *[f"- {warning}" for warning in node.warnings]])
        if node.assumptions:
            sections.extend(["", "## Assumptions", "", *[f"- {assumption}" for assumption in node.assumptions]])
        if node.error:
            sections.extend(["", "## Error", "", node.error])
        if node.error_traceback:
            sections.extend(["", "## Error Traceback", "", node.error_traceback])

        return "\n".join(sections).strip() + "\n"

    def _sync_task_deliverables(self, task: TaskResponse):
        system_root = self._task_system_deliverables_root(task.id)
        shutil.rmtree(system_root, ignore_errors=True)
        system_root.mkdir(parents=True, exist_ok=True)

        if task.result:
            (system_root / "final-deliverable.md").write_text(
                self._render_task_deliverable(task),
                encoding="utf-8",
            )

        nodes = [
            node
            for node in task.execution_plan.nodes
            if node.result or node.error or node.status in {TaskNodeStatus.COMPLETED, TaskNodeStatus.FAILED}
        ]
        if nodes:
            nodes_dir = system_root / "nodes"
            nodes_dir.mkdir(parents=True, exist_ok=True)
            for index, node in enumerate(nodes, start=1):
                filename = f"{index:02d}-{self._sanitize_filename(node.title, fallback='node')}.md"
                (nodes_dir / filename).write_text(self._render_node_deliverable(node), encoding="utf-8")

        if task.error:
            (system_root / "error.txt").write_text(task.error, encoding="utf-8")
        if task.error_traceback:
            (system_root / "error-traceback.txt").write_text(task.error_traceback, encoding="utf-8")

        self._refresh_task_deliverables(task)

    def list_task_deliverables(self, task_id: str) -> list[TaskDeliverable]:
        task = self._tasks.get(task_id)
        if not task:
            return []
        self._refresh_task_deliverables(task)
        return task.deliverables

    def read_task_deliverable(self, task_id: str, relative_path: str) -> dict[str, str]:
        task = self._tasks.get(task_id)
        if not task:
            raise FileNotFoundError("Task not found")

        root = self._task_deliverables_root(task_id).resolve()
        target = (root / relative_path).resolve()
        if not str(target).startswith(str(root)):
            raise PermissionError("Path traversal blocked")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError("Deliverable not found")

        return {
            "path": str(target.relative_to(root)),
            "name": target.name,
            "content": target.read_text(encoding="utf-8"),
        }

    def get_task_deliverable_path(self, task_id: str, relative_path: str) -> Path:
        task = self._tasks.get(task_id)
        if not task:
            raise FileNotFoundError("Task not found")

        root = self._task_deliverables_root(task_id).resolve()
        target = (root / relative_path).resolve()
        if not str(target).startswith(str(root)):
            raise PermissionError("Path traversal blocked")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError("Deliverable not found")
        return target

    def create_task(
        self,
        title: str,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        team_id: Optional[str] = None,
        assigned_agent_id: Optional[str] = None,
        execution_mode: TaskExecutionMode = TaskExecutionMode.AUTO,
        context_document_ids: Optional[list[str]] = None,
    ) -> TaskResponse:
        now = _now_iso()
        active_brief = get_project_context_store().get_active_brief()
        self._task_identifier_counter += 1
        task = TaskResponse(
            id=str(uuid.uuid4()),
            identifier=f"TASK-{self._task_identifier_counter}",
            title=title,
            description=description,
            status=TaskStatus.DRAFTING,
            priority=priority,
            status_changed_at=now,
            assigned_team_id=team_id,
            assigned_agent_id=assigned_agent_id,
            execution_mode=execution_mode,
            context_document_ids=context_document_ids or [],
            brief_revision=active_brief.revision if active_brief else None,
            brief_fingerprint=active_brief.brief_fingerprint if active_brief else None,
            created_at=now,
            updated_at=now,
        )
        self._refresh_task_execution_contract(task)
        self._refresh_task_deliverables(task)
        self._tasks[task.id] = task
        self._save_tasks()
        return task

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        task = self._tasks.get(task_id)
        if task:
            self._refresh_task_execution_contract(task)
            self._refresh_task_deliverables(task)
        return task

    def delete_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status == TaskStatus.DRAFTING and task.execution_plan.status in {
            TaskPlanStatus.PLANNING, TaskPlanStatus.READY, TaskPlanStatus.RUNNING,
        }:
            raise ValueError("Cannot delete a task while it is being drafted.")
        del self._tasks[task_id]
        shutil.rmtree(self.task_deliverables_dir / task_id, ignore_errors=True)
        self._save_tasks()
        return True

    def _check_blocking_relations(self, task_id: str) -> list[str]:
        """Return blocker descriptions if this task is blocked by incomplete tasks."""
        from app.core.task_relation_store import get_task_relation_store
        from app.models.task_relation import RelationType
        store = get_task_relation_store()
        blockers = []
        for rel in store.list_for_task(task_id):
            if rel.type == RelationType.BLOCKS and rel.target_task_id == task_id:
                source = self._tasks.get(rel.source_task_id)
                if source and source.status != TaskStatus.APPROVED:
                    blockers.append(
                        f"Blocked by {source.identifier or source.id[:8]}: {source.title} (status: {source.status.value})"
                    )
        return blockers

    def _unblock_dependent_tasks(self, completed_task_id: str):
        """Refresh eligibility of tasks that were blocked by this now-completed task."""
        from app.core.task_relation_store import get_task_relation_store
        from app.models.task_relation import RelationType
        store = get_task_relation_store()
        for rel in store.list_for_task(completed_task_id):
            if rel.type == RelationType.BLOCKS and rel.source_task_id == completed_task_id:
                dependent = self._tasks.get(rel.target_task_id)
                if dependent:
                    relation_blockers = self._check_blocking_relations(dependent.id)
                    if not relation_blockers:
                        # Only clear if no other blocking relations remain
                        current_blockers = [
                            b for b in dependent.execution_blockers
                            if not b.startswith("Blocked by")
                        ]
                        dependent.execution_blockers = current_blockers
                        if not current_blockers:
                            dependent.execution_eligibility = TaskExecutionEligibility.ELIGIBLE
                    dependent.updated_at = _now_iso()
        self._save_tasks()

    def transition_task_status(self, task_id: str, new_status: TaskStatus) -> TaskResponse:
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if new_status not in self._VALID_TRANSITIONS.get(task.status, set()):
            raise ValueError(
                f"Invalid transition: {task.status.value} → {new_status.value}"
            )
        task.status = new_status
        task.status_changed_at = _now_iso()
        task.updated_at = _now_iso()
        if new_status == TaskStatus.CANCELLED:
            task.cancelled_at = _now_iso()
        # When task is approved, unblock dependents
        if new_status == TaskStatus.APPROVED:
            self._save_tasks()
            self._unblock_dependent_tasks(task_id)
            return self._tasks[task_id]
        self._save_tasks()
        return task

    def patch_task(self, task_id: str, **fields) -> TaskResponse | None:
        task = self._tasks.get(task_id)
        if not task:
            return None
        data = task.model_dump()
        for k, v in fields.items():
            if k in data:
                data[k] = v
        data["updated_at"] = _now_iso()
        updated = TaskResponse.model_validate(data)
        self._tasks[task_id] = updated
        self._save_tasks()
        return updated

    def list_tasks(self) -> list[TaskResponse]:
        tasks = list(self._tasks.values())
        for task in tasks:
            self._refresh_task_execution_contract(task)
            self._refresh_task_deliverables(task)
        return tasks

    def _task_execution_contract(self, task: TaskResponse) -> tuple[TaskExecutionEligibility, list[str]]:
        factory = get_agent_factory()
        blockers: list[str] = []
        if task.assigned_agent_id:
            agent = factory.get_agent(task.assigned_agent_id)
            if not agent:
                blockers.append("L'agent assigné n'est plus disponible.")
        if task.assigned_team_id:
            team = factory.get_team(task.assigned_team_id)
            if not team:
                blockers.append("L'équipe assignée n'est plus disponible.")
        if task.assigned_team_id and task.assigned_agent_id:
            agent = factory.get_agent(task.assigned_agent_id)
            if agent and agent.team_id != task.assigned_team_id:
                blockers.append("L'agent assigné n'appartient pas à l'équipe sélectionnée.")
        if not task.assigned_team_id and not task.assigned_agent_id:
            teams = factory.list_teams()
            if len(teams) > 1:
                blockers.append("Plusieurs équipes existent. Assignez explicitement une équipe ou un agent.")
            elif len(teams) == 0:
                blockers.append("Aucune équipe n'est disponible pour exécuter cette tâche.")
        # Add blocking relations check
        relation_blockers = self._check_blocking_relations(task.id)
        blockers.extend(relation_blockers)

        if blockers:
            has_user_fix = any(
                blocker.startswith("Plusieurs équipes")
                or blocker.startswith("Blocked by")
                or "assign" in blocker.lower()
                or "disponible" in blocker.lower()
                for blocker in blockers
            )
            eligibility = (
                TaskExecutionEligibility.CLARIFICATION_REQUIRED
                if has_user_fix
                else TaskExecutionEligibility.INELIGIBLE
            )
        else:
            eligibility = TaskExecutionEligibility.ELIGIBLE
        return eligibility, blockers

    def _refresh_task_execution_contract(self, task: TaskResponse):
        eligibility, blockers = self._task_execution_contract(task)
        task.execution_eligibility = eligibility
        task.execution_blockers = blockers

    def ensure_task_execution_eligible(self, task: TaskResponse):
        self._refresh_task_execution_contract(task)
        if task.execution_eligibility != TaskExecutionEligibility.ELIGIBLE:
            message = task.execution_blockers[0] if task.execution_blockers else "Task is not eligible for execution."
            raise ValueError(message)

    def _update_task(self, task_id: str, **kwargs):
        task = self._tasks.get(task_id)
        if not task:
            return
        for key, value in kwargs.items():
            setattr(task, key, value)
        task.updated_at = _now_iso()
        self._save_tasks()

    def _add_progress(
        self,
        task_id: str,
        message: str,
        *,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        node_id: Optional[str] = None,
        stage: Optional[str] = None,
        structured_flow: Optional[str] = None,
        structured_channel: Optional[str] = None,
    ):
        task = self._tasks.get(task_id)
        if not task:
            return
        entry = TaskProgressEntry(
            timestamp=_now_iso(),
            message=message,
            agent=agent_name,
            agent_id=agent_id,
            agent_name=agent_name,
            node_id=node_id,
            stage=stage,
            structured_flow=structured_flow,
            structured_channel=structured_channel,
        )
        task.progress_log.append(entry)
        task.updated_at = _now_iso()
        self._save_tasks()

    async def _broadcast_task(self, task_id: str, broadcast: Optional[BroadcastCallback]):
        if broadcast and task_id in self._tasks:
            await broadcast({"type": "task_update", "data": self._tasks[task_id].model_dump()})

    async def _broadcast_node_event(
        self,
        event_type: str,
        task_id: str,
        node: TaskExecutionNode,
        broadcast: Optional[BroadcastCallback],
        *,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ):
        """Broadcast a dedicated node lifecycle event (node_started/node_completed/node_failed)."""
        if not broadcast:
            return
        await broadcast({
            "type": event_type,
            "data": {
                "task_id": task_id,
                "node_id": node.id,
                "node_title": node.title,
                "status": node.status.value,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "quality_score": node.quality_score,
            },
        })

    async def _broadcast_agent_status(self, agent_id: str, broadcast: Optional[BroadcastCallback]):
        if not broadcast:
            return
        agent = get_agent_factory().get_agent(agent_id)
        if not agent:
            return
        await broadcast({"type": "agent_status", "data": build_agent_status_payload(agent)})

    async def _set_agent_occupancy(
        self,
        agent_id: str,
        *,
        occupancy_status: AgentOccupancyStatus,
        occupancy_reason: Optional[AgentOccupancyReason],
        current_task_id: Optional[str],
        current_task_title: Optional[str],
        current_node_id: Optional[str],
        current_node_title: Optional[str],
        busy_since: Optional[str],
        broadcast: Optional[BroadcastCallback],
    ) -> Optional[AgentConfig]:
        agent = get_agent_factory().update_agent_occupancy(
            agent_id,
            occupancy_status=occupancy_status,
            occupancy_reason=occupancy_reason,
            current_task_id=current_task_id,
            current_task_title=current_task_title,
            current_node_id=current_node_id,
            current_node_title=current_node_title,
            busy_since=busy_since,
        )
        if agent:
            await self._broadcast_agent_status(agent_id, broadcast)
        return agent

    async def _clear_task_agent_occupancy(self, task: TaskResponse, broadcast: Optional[BroadcastCallback]):
        factory = get_agent_factory()
        for agent_id in task.assigned_agent_ids:
            agent = factory.get_agent(agent_id)
            if not agent or agent.current_task_id != task.id:
                continue
            factory.clear_agent_occupancy(agent_id)
            await self._broadcast_agent_status(agent_id, broadcast)

    def _agent_has_remaining_work(
        self,
        plan: TaskExecutionPlan,
        agent_id: str,
        *,
        exclude_node_id: Optional[str] = None,
    ) -> bool:
        for plan_node in plan.nodes:
            if plan_node.assigned_agent_id != agent_id:
                continue
            if exclude_node_id and plan_node.id == exclude_node_id:
                continue
            if plan_node.status not in {
                TaskNodeStatus.COMPLETED,
                TaskNodeStatus.FAILED,
                TaskNodeStatus.SKIPPED,
            }:
                return True
        return False

    async def _learn_from_completed_nodes(
        self,
        task: TaskResponse,
        completed_nodes: list[tuple[TaskExecutionNode, AgentConfig]],
        broadcast: Optional[BroadcastCallback],
    ) -> None:
        if not completed_nodes:
            return

        outcomes = await asyncio.gather(
            *[
                run_learn_from_work(cfg, task, node, broadcast_callback=broadcast)
                for node, cfg in completed_nodes
            ],
            return_exceptions=True,
        )
        for (node, cfg), outcome in zip(completed_nodes, outcomes):
            if isinstance(outcome, Exception):
                logger.warning(
                    "Learn-from-work failed for agent %s on node %s: %s",
                    cfg.id,
                    node.id,
                    outcome,
                )

    def _resolve_target_team(self, task: TaskResponse, factory) -> Optional[TeamConfig]:
        if task.assigned_team_id:
            team = factory.get_team(task.assigned_team_id)
            if not team:
                raise ValueError("Assigned team not found.")
            return team

        teams = factory.list_teams()
        if len(teams) == 1:
            task.assigned_team_id = teams[0].id
            return teams[0]

        if len(teams) > 1:
            raise ValueError("Plusieurs équipes existent. Assignez explicitement une équipe à cette tâche.")

        return None

    def _resolve_task_agents(
        self,
        task: TaskResponse,
        factory,
    ) -> tuple[Optional[TeamConfig], Optional[AgentConfig], list[AgentConfig]]:
        if task.assigned_agent_id:
            agent = factory.get_agent(task.assigned_agent_id)
            if not agent:
                raise ValueError("Assigned agent not found.")
            if agent.status == AgentStatus.ERROR:
                raise ValueError("Assigned agent is in error state.")
            if agent.occupancy_status != AgentOccupancyStatus.IDLE:
                raise ValueError("Assigned agent is already occupied.")
            return None, agent, []

        team = self._resolve_target_team(task, factory)
        if not team:
            raise ValueError("Aucun agent ou équipe n'est assigné à cette tâche.")

        ordered_agents = factory.get_ordered_team_agents(team.id)
        if not ordered_agents:
            raise ValueError("Assigned team has no agents.")

        lead = next((agent for agent in ordered_agents if agent.id == team.lead_agent_id), None)
        if not lead:
            raise ValueError("Assigned team has no valid team lead.")

        ready_agents = [
            agent
            for agent in ordered_agents
            if agent.status == AgentStatus.READY and agent.occupancy_status == AgentOccupancyStatus.IDLE
        ]
        if (
            lead not in ready_agents
            and lead.status != AgentStatus.ERROR
            and lead.occupancy_status == AgentOccupancyStatus.IDLE
        ):
            ready_agents = [lead] + [agent for agent in ready_agents if agent.id != lead.id]

        available_agents = ready_agents if ready_agents and lead in ready_agents else [
            agent
            for agent in ordered_agents
            if agent.status != AgentStatus.ERROR and agent.occupancy_status == AgentOccupancyStatus.IDLE
        ]
        if lead not in available_agents:
            raise ValueError("No usable team lead available for this task.")

        specialists = [
            agent for agent in available_agents
            if agent.id != lead.id and agent.role != AgentRole.ASSOCIATE
        ]
        return team, lead, specialists

    async def _plan_with_lead(
        self,
        task: TaskResponse,
        team: TeamConfig,
        lead: AgentConfig,
        specialists: list[AgentConfig],
        project_context_summary: str,
        task_documents_context: str,
    ) -> Optional[dict[str, Any]]:
        if not specialists:
            return None

        model = self.settings.claude_model_opus if lead.model_tier == ModelTier.OPUS else self.settings.claude_model_sonnet

        def _specialist_line(specialist: AgentConfig) -> str:
            score = _get_cached_readiness_score(specialist.id)
            readiness_part = f", readiness: {score}/100" if score is not None else ""
            warning = " ⚠ low readiness" if score is not None and score < 50 else ""
            return (
                f"- {specialist.name} (agent_id: {specialist.id}, title: {specialist.title},"
                f" specialization: {specialist.specialization}{readiness_part}{warning})"
            )

        specialists_text = "\n".join(_specialist_line(s) for s in specialists)
        if not specialists_text:
            return None

        prompt = PLANNER_USER_PROMPT.format(
            task_title=task.title,
            task_description=task.description,
            requested_mode=task.execution_mode.value,
            project_context=project_context_summary,
            task_documents=task_documents_context or "No explicit task documents.",
            team_name=team.name,
            team_description=team.description,
            team_scope=team.scope_note or "No explicit scope note",
            lead_name=lead.name,
            lead_id=lead.id,
            lead_title=lead.title,
            lead_specialization=lead.specialization,
            specialists=specialists_text,
        )

        try:
            client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
            structured = await request_structured_json_async(
                client=client,
                model=model,
                prompt=prompt,
                response_model=_PlannerPayload,
                schema_hint=PLANNER_SCHEMA_HINT,
                max_tokens=ORCHESTRATOR_PLANNER_MAX_TOKENS,
                repair_max_tokens=ORCHESTRATOR_PLANNER_REPAIR_MAX_TOKENS,
                request_name=f"task_planner:{task.id}",
                system=PLANNER_SYSTEM_PROMPT,
            )
            telemetry = getattr(structured, "telemetry", None)
            structured_channel = getattr(telemetry, "generation_channel", None) or "text_json"
            self._add_progress(
                task.id,
                f"Plan généré via le canal structuré {structured_channel}.",
                agent_id=lead.id,
                agent_name=lead.name,
                stage="task_planner_structured",
                structured_flow="task_planner",
                structured_channel=structured_channel,
            )
            return structured.value.model_dump(mode="json")
        except StructuredJsonError as exc:
            self._add_progress(
                task.id,
                f"Plan structuré indisponible, fallback local après échec du canal {exc.telemetry.generation_channel}.",
                agent_id=lead.id,
                agent_name=lead.name,
                stage="task_planner_fallback",
                structured_flow="task_planner",
                structured_channel=exc.telemetry.generation_channel,
            )
            logger.warning(
                "Lead planning failed for task %s: %s (preview=%r, parse_error=%s, repair_error=%s)",
                task.id,
                exc,
                exc.telemetry.raw_preview,
                exc.telemetry.parse_error,
                exc.telemetry.repair_error,
            )
            return None
        except Exception as exc:
            logger.warning("Lead planning failed for task %s: %s", task.id, exc)
            return None

    def _node_from_blueprint(
        self,
        blueprint_node: dict[str, Any],
        specialist: AgentConfig,
    ) -> TaskExecutionNode:
        title = str(blueprint_node.get("title") or f"{specialist.title} contribution").strip()
        brief = str(blueprint_node.get("brief") or "").strip()
        if not brief:
            brief = (
                f"Contribute only the part of the root task that belongs to your specialization "
                f"({specialist.specialization}). Deliver a focused output that the lead can compile."
            )
        return TaskExecutionNode(
            id=str(uuid.uuid4()),
            title=title,
            description=brief,
            node_type=TaskNodeType.SPECIALIST,
            status=TaskNodeStatus.PENDING,
            assigned_agent_id=specialist.id,
            assigned_agent_name=specialist.name,
        )

    def _build_default_plan(
        self,
        task: TaskResponse,
        lead: AgentConfig,
        specialists: list[AgentConfig],
    ) -> TaskExecutionPlan:
        if not specialists:
            return TaskExecutionPlan(
                status=TaskPlanStatus.READY,
                mode=TaskExecutionMode.STANDALONE,
                compiler_agent_id=lead.id,
                compiler_agent_name=lead.name,
                planning_notes="No specialist breakdown required; lead executes the task directly.",
                nodes=[
                    TaskExecutionNode(
                        id=str(uuid.uuid4()),
                        title=lead.title,
                        description=task.description,
                        node_type=TaskNodeType.SINGLE_AGENT,
                        status=TaskNodeStatus.READY,
                        assigned_agent_id=lead.id,
                        assigned_agent_name=lead.name,
                    )
                ],
            )

        specialist_nodes = [
            TaskExecutionNode(
                id=str(uuid.uuid4()),
                title=f"{specialist.title} contribution",
                description=(
                    f"Contribute only the part of the root task that belongs to your specialization "
                    f"({specialist.specialization}). Produce a focused output that the lead can integrate."
                ),
                node_type=TaskNodeType.SPECIALIST,
                status=TaskNodeStatus.READY,
                assigned_agent_id=specialist.id,
                assigned_agent_name=specialist.name,
            )
            for specialist in specialists
        ]
        compile_node = TaskExecutionNode(
            id=str(uuid.uuid4()),
            title=f"{lead.title} final compilation",
            description="Compile the final deliverable from the completed specialist outputs.",
            node_type=TaskNodeType.LEAD_COMPILE,
            status=TaskNodeStatus.BLOCKED,
            assigned_agent_id=lead.id,
            assigned_agent_name=lead.name,
            depends_on=[node.id for node in specialist_nodes],
        )
        return TaskExecutionPlan(
            status=TaskPlanStatus.READY,
            mode=TaskExecutionMode.STANDALONE,
            compiler_agent_id=lead.id,
            compiler_agent_name=lead.name,
            planning_notes="Default star execution plan: specialists work independently, then the lead compiles.",
            nodes=[*specialist_nodes, compile_node],
        )

    def _resolve_plan_mode(
        self,
        task: TaskResponse,
        dependencies_detected: bool,
    ) -> TaskExecutionMode:
        if task.execution_mode == TaskExecutionMode.STANDALONE:
            return TaskExecutionMode.STANDALONE
        if dependencies_detected:
            return TaskExecutionMode.DEPENDENCY_GRAPH
        return TaskExecutionMode.STANDALONE

    def _validate_execution_plan(self, plan: TaskExecutionPlan) -> None:
        nodes_by_id = {node.id: node for node in plan.nodes}
        indegree = {node.id: 0 for node in plan.nodes}
        adjacency: dict[str, list[str]] = {node.id: [] for node in plan.nodes}

        for node in plan.nodes:
            for dependency_id in node.depends_on:
                if dependency_id not in nodes_by_id:
                    raise ValueError(f"Unknown dependency node: {dependency_id}")
                adjacency[dependency_id].append(node.id)
                indegree[node.id] += 1

        queue = [node_id for node_id, degree in indegree.items() if degree == 0]
        visited = 0
        while queue:
            current = queue.pop(0)
            visited += 1
            for downstream in adjacency[current]:
                indegree[downstream] -= 1
                if indegree[downstream] == 0:
                    queue.append(downstream)

        if visited != len(plan.nodes):
            raise ValueError("Execution plan contains a dependency cycle.")

    def _build_plan_from_blueprint(
        self,
        task: TaskResponse,
        lead: AgentConfig,
        specialists: list[AgentConfig],
        blueprint: Optional[dict[str, Any]],
    ) -> TaskExecutionPlan:
        if not specialists:
            return self._build_default_plan(task, lead, specialists)

        specialists_by_id = {specialist.id: specialist for specialist in specialists}
        if not blueprint:
            return self._build_default_plan(task, lead, specialists)

        raw_mode = str(blueprint.get("mode") or "").strip().lower()
        requested_dependency_mode = task.execution_mode in {TaskExecutionMode.AUTO, TaskExecutionMode.DEPENDENCY_GRAPH}
        allow_dependencies = requested_dependency_mode and task.execution_mode != TaskExecutionMode.STANDALONE
        planning_notes = str(blueprint.get("planning_notes") or "").strip()

        nodes_by_agent_id: dict[str, TaskExecutionNode] = {}
        raw_dependencies: dict[str, list[str]] = {}
        for item in blueprint.get("nodes", []):
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("agent_id") or "").strip()
            specialist = specialists_by_id.get(agent_id)
            if not specialist or agent_id in nodes_by_agent_id:
                continue
            node = self._node_from_blueprint(item, specialist)
            nodes_by_agent_id[agent_id] = node
            depends_on = item.get("depends_on") or []
            if isinstance(depends_on, list):
                raw_dependencies[agent_id] = [str(dep).strip() for dep in depends_on if str(dep).strip()]
            else:
                raw_dependencies[agent_id] = []

        if not nodes_by_agent_id:
            return self._build_default_plan(task, lead, specialists)

        for agent_id, node in nodes_by_agent_id.items():
            dependency_node_ids: list[str] = []
            for dependency_agent_id in raw_dependencies.get(agent_id, []):
                if not allow_dependencies:
                    continue
                dependency_node = nodes_by_agent_id.get(dependency_agent_id)
                if dependency_node and dependency_node.id != node.id:
                    dependency_node_ids.append(dependency_node.id)
            node.depends_on = list(dict.fromkeys(dependency_node_ids))
            node.status = TaskNodeStatus.BLOCKED if node.depends_on else TaskNodeStatus.READY

        specialist_nodes = list(nodes_by_agent_id.values())
        dependencies_detected = any(node.depends_on for node in specialist_nodes)

        compile_node = TaskExecutionNode(
            id=str(uuid.uuid4()),
            title=f"{lead.title} final compilation",
            description="Compile the final deliverable from the completed dependency outputs.",
            node_type=TaskNodeType.LEAD_COMPILE,
            status=TaskNodeStatus.BLOCKED,
            assigned_agent_id=lead.id,
            assigned_agent_name=lead.name,
            depends_on=[node.id for node in specialist_nodes],
        )
        resolved_mode = self._resolve_plan_mode(task, dependencies_detected or raw_mode == TaskExecutionMode.DEPENDENCY_GRAPH.value)
        plan = TaskExecutionPlan(
            status=TaskPlanStatus.READY,
            mode=resolved_mode,
            compiler_agent_id=lead.id,
            compiler_agent_name=lead.name,
            planning_notes=planning_notes or "Lead-generated execution plan accepted.",
            nodes=[*specialist_nodes, compile_node],
        )
        self._validate_execution_plan(plan)
        return plan

    async def _build_execution_plan(
        self,
        task: TaskResponse,
        team: Optional[TeamConfig],
        lead: AgentConfig,
        specialists: list[AgentConfig],
        ctx_store,
        doc_store: DocumentStore,
    ) -> TaskExecutionPlan:
        project_context_summary = _project_context_summary(ctx_store.load_context() or {})
        task_documents_context = _format_explicit_documents_context(doc_store, task.context_document_ids)

        if not team:
            return TaskExecutionPlan(
                status=TaskPlanStatus.READY,
                mode=TaskExecutionMode.STANDALONE,
                compiler_agent_id=lead.id,
                compiler_agent_name=lead.name,
                planning_notes="Direct agent task.",
                nodes=[
                    TaskExecutionNode(
                        id=str(uuid.uuid4()),
                        title=lead.title,
                        description=task.description,
                        node_type=TaskNodeType.SINGLE_AGENT,
                        status=TaskNodeStatus.READY,
                        assigned_agent_id=lead.id,
                        assigned_agent_name=lead.name,
                    )
                ],
            )

        blueprint = await self._plan_with_lead(
            task,
            team,
            lead,
            specialists,
            project_context_summary,
            task_documents_context,
        )
        try:
            return self._build_plan_from_blueprint(task, lead, specialists, blueprint)
        except Exception as exc:
            logger.warning("Invalid lead-generated plan for task %s, falling back to default: %s", task.id, exc)
            return self._build_default_plan(task, lead, specialists)

    async def _run_single_node(
        self,
        task: TaskResponse,
        node: TaskExecutionNode,
        cfg: AgentConfig,
        task_context_pack: str,
        plan: TaskExecutionPlan,
        skills_store,
        broadcast: Optional[BroadcastCallback],
    ) -> tuple[str, list[str], list[str], list[str], int, list[str]]:
        _summarize_client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        dependency_context_text = await _async_dependency_context(
            plan, node,
            client=_summarize_client,
            model=self.settings.claude_model_sonnet,
        )
        requires_external_research = (
            node.node_type != TaskNodeType.LEAD_COMPILE
            and _classify_task(f"{task.description}\n{node.description}") == "external_fact_task"
        )
        if requires_external_research and has_web_search(self.settings):
            os.environ["SERPER_API_KEY"] = self.settings.serper_api_key

        try:
            native_tools = get_tools_for_agent_native(
                cfg.tools,
                workspace_path=cfg.workspace_path,
                git_bindings=cfg.git_bindings,
                mcp_tool_bindings=cfg.mcp_tool_bindings,
                allow_git_write=True,
            )
            task_root = self._task_deliverables_root(task.id)
            native_tools.extend([
                _build_task_deliverable_write_tool(task_root),
                _build_task_deliverable_list_tool(task_root),
                _build_task_deliverable_read_tool(task_root),
            ])
            system_prompt = await _enrich_backstory(
                cfg, skills_store,
                task_context=f"{task.title}: {node.description}",
            )
            user_message = _prompt_for_node(
                task,
                node,
                cfg,
                task_context_pack,
                dependency_context_text,
                requires_external_research,
            )
            model_name = (
                self.settings.claude_model_opus
                if cfg.model_tier == ModelTier.OPUS
                else self.settings.claude_model_sonnet
            )
            # Capture debug context for the context debug view
            node.debug_system_prompt = system_prompt
            node.debug_user_message = user_message
            node.debug_tools = [t.name for t in native_tools]
            node.debug_model = model_name
        except Exception as exc:
            raise _TaskExecutionFailure(
                _format_failure_message(type(exc).__name__, str(exc)),
                error_type=type(exc).__name__,
                error_traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip(),
                failure_stage="node_setup",
            ) from exc

        usage_tracker = get_usage_tracker()
        client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        runner = AnthropicAgentRunner(client=client)

        async def on_chunk(chunk: str) -> None:
            if broadcast:
                await broadcast({
                    "type": "node_stream_chunk",
                    "data": {"node_id": node.id, "chunk": chunk},
                })

        try:
            result_text, inp_tokens, out_tokens = await runner.run(
                system_prompt=system_prompt,
                user_message=user_message,
                tools=native_tools,
                model=model_name,
                max_tokens=cfg.max_tokens,
                max_iter=cfg.max_iter,
                on_text_chunk=on_chunk,
            )
            usage_tracker.log(model_name, inp_tokens, out_tokens)
            node.debug_input_tokens = inp_tokens
            node.debug_output_tokens = out_tokens
            # Accumulate actual cost on the task
            task.actual_input_tokens += inp_tokens
            task.actual_output_tokens += out_tokens
            task.actual_cost_usd = round(
                task.actual_cost_usd + _tracker_cost_usd(model_name, inp_tokens, out_tokens), 6
            )
            sources, assumptions, warnings = await self._extract_result_metadata(
                result_text,
                task_id=task.id,
                node_id=node.id,
            )
            quality_score, quality_flags = _compute_quality_gate(
                result_text, sources, assumptions, warnings,
            )
            return result_text, sources, assumptions, warnings, quality_score, quality_flags
        except AgentMaxIterError as exc:
            raise _TaskExecutionFailure(
                _format_failure_message("AgentMaxIterError", str(exc)),
                error_type="AgentMaxIterError",
                error_traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip(),
                failure_stage="agent_run",
            ) from exc
        except Exception as exc:
            raise _TaskExecutionFailure(
                _format_failure_message(type(exc).__name__, str(exc)),
                error_type=type(exc).__name__,
                error_traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip(),
                failure_stage="agent_run",
            ) from exc
        finally:
            if self._agent_has_remaining_work(plan, cfg.id, exclude_node_id=node.id):
                await self._set_agent_occupancy(
                    cfg.id,
                    occupancy_status=AgentOccupancyStatus.ASSIGNED,
                    occupancy_reason=AgentOccupancyReason.TASK_EXECUTION,
                    current_task_id=task.id,
                    current_task_title=task.title,
                    current_node_id=None,
                    current_node_title=None,
                    busy_since=node.started_at or _now_iso(),
                    broadcast=broadcast,
                )
            else:
                get_agent_factory().clear_agent_occupancy(cfg.id)
                await self._broadcast_agent_status(cfg.id, broadcast)

    async def _extract_result_metadata(
        self,
        result_text: str,
        *,
        task_id: str,
        node_id: str,
    ) -> tuple[list[str], list[str], list[str]]:
        fallback_metadata = _parse_result_metadata(result_text)
        if not self.settings.anthropic_api_key or not result_text.strip():
            return fallback_metadata

        prompt = RESULT_METADATA_PROMPT.format(
            result_text=result_text.strip()[:12000],
        )
        try:
            client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
            structured = await request_structured_json_async(
                client=client,
                model=self.settings.claude_model_sonnet,
                prompt=prompt,
                response_model=_TaskResultMetadataPayload,
                schema_hint=RESULT_METADATA_SCHEMA_HINT,
                max_tokens=ORCHESTRATOR_RESULT_METADATA_MAX_TOKENS,
                repair_max_tokens=ORCHESTRATOR_RESULT_METADATA_REPAIR_MAX_TOKENS,
                request_name=f"task_result_metadata:{node_id}",
            )
            telemetry = getattr(structured, "telemetry", None)
            structured_channel = getattr(telemetry, "generation_channel", None) or "text_json"
            self._add_progress(
                task_id,
                f"Métadonnées de résultat extraites via le canal structuré {structured_channel}.",
                node_id=node_id,
                stage="task_result_metadata_structured",
                structured_flow="task_result_metadata",
                structured_channel=structured_channel,
            )
            return (
                structured.value.sources,
                structured.value.assumptions,
                structured.value.warnings,
            )
        except StructuredJsonError as exc:
            self._add_progress(
                task_id,
                f"Extraction structurée des métadonnées indisponible, fallback local après échec du canal {exc.telemetry.generation_channel}.",
                node_id=node_id,
                stage="task_result_metadata_fallback",
                structured_flow="task_result_metadata",
                structured_channel=exc.telemetry.generation_channel,
            )
            logger.warning(
                "task_result_metadata fallback_used node=%s parse_failed=%s repair_attempted=%s repair_succeeded=%s parse_error=%s repair_error=%s preview=%r",
                node_id,
                exc.telemetry.parse_failed,
                exc.telemetry.repair_attempted,
                exc.telemetry.repair_succeeded,
                exc.telemetry.parse_error,
                exc.telemetry.repair_error,
                exc.telemetry.raw_preview,
            )
        except Exception as exc:
            logger.warning("task_result_metadata unexpected_error node=%s error=%s", node_id, exc)
        return fallback_metadata

    def _mark_ready_nodes(self, plan: TaskExecutionPlan):
        for node in plan.nodes:
            if node.status not in {TaskNodeStatus.BLOCKED, TaskNodeStatus.PENDING}:
                continue
            dependencies_satisfied = all(
                dependency.status == TaskNodeStatus.COMPLETED
                for dependency in plan.nodes
                if dependency.id in node.depends_on
            )
            if dependencies_satisfied:
                node.status = TaskNodeStatus.READY

    def _skip_remaining_nodes(self, plan: TaskExecutionPlan, reason: str):
        skipped_details = _FailureDetails(
            error=reason,
            error_type="UpstreamNodeFailure",
            error_traceback=None,
            failure_stage="skipped_after_upstream_failure",
        )
        for node in plan.nodes:
            if node.status in {TaskNodeStatus.PENDING, TaskNodeStatus.BLOCKED, TaskNodeStatus.READY}:
                node.status = TaskNodeStatus.SKIPPED
                _apply_failure_details(node, skipped_details)
                node.completed_at = _now_iso()

    def _get_transitive_dependents(self, plan: TaskExecutionPlan, failed_ids: set[str]) -> set[str]:
        """Return all node IDs that transitively depend on any failed node."""
        dependents: set[str] = set()
        changed = True
        while changed:
            changed = False
            for node in plan.nodes:
                if node.id in dependents or node.id in failed_ids:
                    continue
                if any(d in failed_ids or d in dependents for d in node.depends_on):
                    dependents.add(node.id)
                    changed = True
        return dependents

    def _skip_dependent_nodes(self, plan: TaskExecutionPlan, failed_ids: set[str]):
        """Skip only the nodes that transitively depend on failed nodes."""
        to_skip = self._get_transitive_dependents(plan, failed_ids)
        details = _FailureDetails(
            error="Skipped because an upstream node failed.",
            error_type="UpstreamNodeFailure",
            error_traceback=None,
            failure_stage="skipped_after_upstream_failure",
        )
        for node in plan.nodes:
            if node.id in to_skip and node.status in {
                TaskNodeStatus.PENDING, TaskNodeStatus.BLOCKED, TaskNodeStatus.READY,
            }:
                node.status = TaskNodeStatus.SKIPPED
                _apply_failure_details(node, details)
                node.completed_at = _now_iso()

    async def rerun_node(
        self,
        task_id: str,
        node_id: str,
        additional_instructions: Optional[str] = None,
        broadcast: Optional[BroadcastCallback] = None,
    ) -> None:
        """Re-execute a single node within an already-executed task."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        plan = task.execution_plan
        node = next((n for n in plan.nodes if n.id == node_id), None)
        if not node:
            raise ValueError(f"Node {node_id} not found in task {task_id}")
        if node.status not in {TaskNodeStatus.COMPLETED, TaskNodeStatus.FAILED, TaskNodeStatus.SKIPPED}:
            raise ValueError(f"Node {node_id} is in state {node.status} — only terminal nodes can be rerun")

        # Reset the node
        node.status = TaskNodeStatus.READY
        node.result = None
        node.error = None
        node.error_type = None
        node.error_traceback = None
        node.failure_stage = None
        node.started_at = None
        node.completed_at = None
        node.sources = []
        node.assumptions = []
        node.warnings = []
        node.quality_score = None
        node.quality_flags = []
        node.debug_system_prompt = None
        node.debug_user_message = None
        node.debug_tools = []
        node.debug_input_tokens = None
        node.debug_output_tokens = None
        node.debug_model = None
        node.rerun_count += 1
        node.additional_instructions = additional_instructions or None

        # Put task back in executing state
        task.status = TaskStatus.DRAFTING
        plan.status = TaskPlanStatus.RUNNING
        _clear_failure_details(task)
        task.updated_at = _now_iso()
        self._add_progress(
            task_id,
            f"Rerunning node: {node.title}" + (f" (with additional instructions)" if additional_instructions else ""),
            node_id=node.id,
            stage="node_rerun",
        )
        self._save_tasks()
        await self._broadcast_task(task_id, broadcast)

        # Resolve the agent config for this node
        factory = get_agent_factory()
        skills_store = get_skills_store()
        ctx_store = get_project_context_store()
        doc_store = get_document_store()

        cfg = factory.get_agent(node.assigned_agent_id)
        if not cfg:
            node.status = TaskNodeStatus.FAILED
            node.error = f"Agent {node.assigned_agent_id} not found"
            node.error_type = "AgentNotFound"
            node.failure_stage = "node_rerun_setup"
            node.completed_at = _now_iso()
            task.status = TaskStatus.IN_REVIEW  # don't fail the whole task
            plan.status = TaskPlanStatus.COMPLETED
            self._save_tasks()
            await self._broadcast_task(task_id, broadcast)
            return

        team = self._resolve_target_team(task, factory) if task.assigned_team_id else None
        task_context_pack = _build_task_context_pack(task, team, ctx_store, doc_store)

        node.status = TaskNodeStatus.RUNNING
        node.started_at = _now_iso()
        self._save_tasks()
        await self._broadcast_task(task_id, broadcast)

        try:
            result_text, sources, assumptions, warnings, quality_score, quality_flags = (
                await self._run_single_node(
                    task, node, cfg, task_context_pack, plan, skills_store, broadcast,
                )
            )
            node.status = TaskNodeStatus.COMPLETED
            node.result = result_text
            _clear_failure_details(node)
            node.completed_at = _now_iso()
            node.sources = sources
            node.assumptions = assumptions
            node.warnings = warnings
            node.quality_score = quality_score
            node.quality_flags = quality_flags
            self._add_progress(
                task_id,
                f"Node rerun completed: {node.title}",
                agent_id=cfg.id,
                agent_name=cfg.name,
                node_id=node.id,
                stage="node_rerun_completed",
            )

            # If this is the lead_compile node, update the task result
            if node.node_type == TaskNodeType.LEAD_COMPILE:
                task.result = result_text
                task.sources = sources
                task.assumptions = assumptions
                task.warnings = warnings

        except Exception as exc:
            details = _capture_failure_details(exc)
            node.status = TaskNodeStatus.FAILED
            _apply_failure_details(node, details)
            node.completed_at = _now_iso()
            self._add_progress(
                task_id,
                f"Node rerun failed: {node.title} — {details.error}",
                agent_id=cfg.id,
                agent_name=cfg.name,
                node_id=node.id,
                stage="node_rerun_failed",
            )

        # Restore task to completed/failed based on overall state
        all_nodes_terminal = all(
            n.status in {TaskNodeStatus.COMPLETED, TaskNodeStatus.FAILED, TaskNodeStatus.SKIPPED}
            for n in plan.nodes
        )
        if all_nodes_terminal:
            any_failed = any(n.status == TaskNodeStatus.FAILED for n in plan.nodes)
            task.status = TaskStatus.IN_REVIEW
            plan.status = TaskPlanStatus.FAILED if any_failed else TaskPlanStatus.COMPLETED

        task.updated_at = _now_iso()
        self._sync_task_deliverables(task)
        self._save_tasks()
        await self._broadcast_task(task_id, broadcast)

        # Learn from work if successful
        if node.status == TaskNodeStatus.COMPLETED:
            await self._learn_from_completed_nodes(task, [(node, cfg)], broadcast)

    # ──────────────────────────────────────────────────────────────────────
    # Review iteration helpers
    # ──────────────────────────────────────────────────────────────────────

    async def iterate_task(
        self,
        task_id: str,
        feedback: str,
        broadcast: Optional[BroadcastCallback] = None,
    ) -> None:
        """Re-execute the compile node with PM feedback, incrementing the iteration counter."""
        from app.core.task_comment_store import get_task_comment_store
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if task.status != TaskStatus.IN_REVIEW:
            raise ValueError("Task must be in review to iterate")

        task.current_iteration += 1
        get_task_comment_store().create_comment(task_id, TaskCommentCreate(
            body=feedback,
            author_type=CommentAuthorType.HUMAN,
            author_name="PM",
            comment_type=CommentType.REVIEW_FEEDBACK,
        ))

        lead_node = next(
            (n for n in task.execution_plan.nodes if n.node_type == TaskNodeType.LEAD_COMPILE),
            task.execution_plan.nodes[-1] if task.execution_plan.nodes else None,
        )
        if not lead_node:
            raise ValueError("No executable node found for iteration")

        feedback_instructions = (
            f"PM FEEDBACK (iteration {task.current_iteration}):\n{feedback}\n\n"
            "Re-compile the result addressing this feedback. "
            "Use the existing specialist outputs as input."
        )
        await self.rerun_node(
            task_id,
            lead_node.id,
            additional_instructions=feedback_instructions,
            broadcast=broadcast,
        )


    async def execute_task(self, task_id: str, broadcast: Optional[BroadcastCallback] = None):
        task = self._tasks.get(task_id)
        if not task:
            logger.error("Task %s not found", task_id)
            return
        # Status guard: only allow execution from QUEUED or REVIEW (re-iteration)
        if task.status not in {TaskStatus.DRAFTING, TaskStatus.IN_REVIEW}:
            raise ValueError(f"Cannot execute task in status '{task.status.value}'.")
        self._refresh_task_execution_contract(task)
        if task.execution_eligibility != TaskExecutionEligibility.ELIGIBLE:
            blocker = task.execution_blockers[0] if task.execution_blockers else "Task is not eligible for execution."
            logger.warning("Task %s blocked before execution: %s", task_id, blocker)
            self._add_progress(task_id, blocker, stage="execution_guard")
            self._save_tasks()
            await self._broadcast_task(task_id, broadcast)
            raise ValueError(blocker)

        factory = get_agent_factory()
        skills_store = get_skills_store()
        ctx_store = get_project_context_store()
        doc_store = get_document_store()

        task.status = TaskStatus.DRAFTING
        task.status_changed_at = _now_iso()
        task.current_iteration += 1
        _clear_failure_details(task)
        task.result = None
        task.execution_plan = TaskExecutionPlan(status=TaskPlanStatus.PLANNING, mode=task.execution_mode)
        task.progress_log = []
        task.sources = []
        task.assumptions = []
        task.warnings = []
        task.assigned_agent_ids = []
        task.updated_at = _now_iso()
        self._sync_task_deliverables(task)
        self._save_tasks()
        self._add_progress(task_id, "Task started", stage="task_start")
        await self._broadcast_task(task_id, broadcast)

        try:
            team, lead, specialists = self._resolve_task_agents(task, factory)
            plan = await self._build_execution_plan(task, team, lead, specialists, ctx_store, doc_store)
            task.execution_plan = plan
            task.execution_plan.status = TaskPlanStatus.READY
            # Estimate cost now that we know the plan structure
            from app.core.cost_estimator import estimate_task_cost
            est_in, est_out, est_cost = estimate_task_cost(plan)
            task.estimated_input_tokens = est_in
            task.estimated_output_tokens = est_out
            task.estimated_cost_usd = est_cost
            task.assigned_team_id = team.id if team else task.assigned_team_id
            task.assigned_agent_id = lead.id if not team else task.assigned_agent_id
            task.assigned_agent_ids = list(dict.fromkeys(
                node.assigned_agent_id for node in plan.nodes if node.assigned_agent_id
            ))
            assigned_since = _now_iso()
            for agent_id in task.assigned_agent_ids:
                if not agent_id:
                    continue
                await self._set_agent_occupancy(
                    agent_id,
                    occupancy_status=AgentOccupancyStatus.ASSIGNED,
                    occupancy_reason=AgentOccupancyReason.TASK_EXECUTION,
                    current_task_id=task.id,
                    current_task_title=task.title,
                    current_node_id=None,
                    current_node_title=None,
                    busy_since=assigned_since,
                    broadcast=broadcast,
                )
            self._add_progress(
                task_id,
                f"Execution plan ready: {len(plan.nodes)} node(s), mode={plan.mode.value}",
                agent_id=lead.id,
                agent_name=lead.name,
                stage="planning",
            )
            self._save_tasks()
            await self._broadcast_task(task_id, broadcast)

            task_context_pack = _build_task_context_pack(task, team, ctx_store, doc_store)
            task.execution_plan.status = TaskPlanStatus.RUNNING
            self._save_tasks()
            await self._broadcast_task(task_id, broadcast)

            all_wave_failures: list[_WaveNodeFailure] = []

            while True:
                ready_nodes = [node for node in task.execution_plan.nodes if node.status == TaskNodeStatus.READY]
                if not ready_nodes:
                    running_nodes = [node for node in task.execution_plan.nodes if node.status == TaskNodeStatus.RUNNING]
                    if running_nodes:
                        await asyncio.sleep(0)
                        continue

                    incomplete_nodes = [
                        node for node in task.execution_plan.nodes
                        if node.status not in {TaskNodeStatus.COMPLETED, TaskNodeStatus.SKIPPED, TaskNodeStatus.FAILED}
                    ]
                    if incomplete_nodes:
                        raise ValueError("Execution plan is stuck: no ready nodes and some nodes remain incomplete.")
                    break

                for node in ready_nodes:
                    cfg = factory.get_agent(node.assigned_agent_id) if node.assigned_agent_id else None
                    node.status = TaskNodeStatus.RUNNING
                    node.started_at = _now_iso()
                    _clear_failure_details(node)
                    if cfg:
                        await self._set_agent_occupancy(
                            cfg.id,
                            occupancy_status=AgentOccupancyStatus.BUSY,
                            occupancy_reason=AgentOccupancyReason.TASK_EXECUTION,
                            current_task_id=task.id,
                            current_task_title=task.title,
                            current_node_id=node.id,
                            current_node_title=node.title,
                            busy_since=node.started_at,
                            broadcast=broadcast,
                        )
                    self._add_progress(
                        task_id,
                        f"Node started: {node.title}",
                        agent_id=cfg.id if cfg else None,
                        agent_name=cfg.name if cfg else node.assigned_agent_name,
                        node_id=node.id,
                        stage="node_start",
                    )

                self._save_tasks()
                await self._broadcast_task(task_id, broadcast)
                for node in ready_nodes:
                    cfg = factory.get_agent(node.assigned_agent_id) if node.assigned_agent_id else None
                    await self._broadcast_node_event(
                        "node_started", task_id, node, broadcast,
                        agent_id=cfg.id if cfg else None,
                        agent_name=cfg.name if cfg else node.assigned_agent_name,
                    )

                wave_coroutines = []
                wave_cfgs: list[AgentConfig] = []
                for node in ready_nodes:
                    cfg = factory.get_agent(node.assigned_agent_id) if node.assigned_agent_id else None
                    if not cfg:
                        wave_coroutines.append(asyncio.sleep(0, result=RuntimeError("Assigned agent not found.")))
                        wave_cfgs.append(lead)
                        continue
                    wave_cfgs.append(cfg)
                    wave_coroutines.append(
                        self._run_single_node(
                            task,
                            node,
                            cfg,
                            task_context_pack,
                            task.execution_plan,
                            skills_store,
                            broadcast,
                        )
                    )

                wave_results = await asyncio.gather(*wave_coroutines, return_exceptions=True)

                wave_failures: list[_WaveNodeFailure] = []
                for node, cfg, outcome in zip(ready_nodes, wave_cfgs, wave_results):
                    if isinstance(outcome, Exception):
                        details = _capture_failure_details(outcome)
                        node.status = TaskNodeStatus.FAILED
                        _apply_failure_details(node, details)
                        node.completed_at = _now_iso()
                        wave_failures.append(_WaveNodeFailure(node=node, agent=cfg, details=details, cause=outcome))
                        self._add_progress(
                            task_id,
                            f"Node failed: {node.title} — {details.error}",
                            agent_id=cfg.id,
                            agent_name=cfg.name,
                            node_id=node.id,
                            stage="node_failed",
                        )
                        self._save_tasks()
                        await self._broadcast_task(task_id, broadcast)
                        await self._broadcast_node_event(
                            "node_failed", task_id, node, broadcast,
                            agent_id=cfg.id if cfg else None,
                            agent_name=cfg.name if cfg else node.assigned_agent_name,
                        )
                        continue

                    result_text, sources, assumptions, warnings, quality_score, quality_flags = outcome

                    node.status = TaskNodeStatus.COMPLETED
                    node.result = result_text
                    _clear_failure_details(node)
                    node.completed_at = _now_iso()
                    node.sources = sources
                    node.assumptions = assumptions
                    node.warnings = warnings
                    node.quality_score = quality_score
                    node.quality_flags = quality_flags
                    self._add_progress(
                        task_id,
                        f"Node completed: {node.title}",
                        agent_id=cfg.id,
                        agent_name=cfg.name,
                        node_id=node.id,
                        stage="node_completed",
                    )
                    if quality_score < 40:
                        self._add_progress(
                            task_id,
                            f"Score qualité bas : {quality_score}/100 — {'; '.join(quality_flags)}",
                            node_id=node.id,
                            stage="quality_gate_low",
                        )
                    self._save_tasks()
                    await self._broadcast_task(task_id, broadcast)
                    await self._broadcast_node_event(
                        "node_completed", task_id, node, broadcast,
                        agent_id=cfg.id if cfg else None,
                        agent_name=cfg.name if cfg else node.assigned_agent_name,
                    )

                if wave_failures:
                    failed_ids = {f.node.id for f in wave_failures}
                    self._skip_dependent_nodes(task.execution_plan, failed_ids)
                    self._mark_ready_nodes(task.execution_plan)
                    self._sync_task_deliverables(task)
                    self._save_tasks()
                    await self._broadcast_task(task_id, broadcast)
                    all_wave_failures.extend(wave_failures)
                    continue

                self._mark_ready_nodes(task.execution_plan)
                self._sync_task_deliverables(task)
                self._save_tasks()
                await self._broadcast_task(task_id, broadcast)
                completed_learning_targets = [
                    (node, cfg)
                    for node, cfg in zip(ready_nodes, wave_cfgs)
                    if node.status == TaskNodeStatus.COMPLETED
                ]
                await self._learn_from_completed_nodes(task, completed_learning_targets, broadcast)

            completed_nodes = [node for node in task.execution_plan.nodes if node.status == TaskNodeStatus.COMPLETED]
            failed_nodes = [
                node for node in task.execution_plan.nodes
                if node.status in {TaskNodeStatus.FAILED, TaskNodeStatus.SKIPPED}
            ]

            if not completed_nodes:
                task.execution_plan.status = TaskPlanStatus.FAILED
                task.status = TaskStatus.IN_REVIEW
                task.status_changed_at = _now_iso()
                if all_wave_failures:
                    raise _build_wave_failure(all_wave_failures) from all_wave_failures[0].cause
                raise ValueError("No execution node completed successfully.")

            if failed_nodes:
                task.execution_plan.status = TaskPlanStatus.PARTIAL
                task.status = TaskStatus.IN_REVIEW
                task.status_changed_at = _now_iso()
            else:
                task.execution_plan.status = TaskPlanStatus.COMPLETED
                task.status = TaskStatus.IN_REVIEW

            task.status_changed_at = _now_iso()
            final_node = next(
                (node for node in reversed(task.execution_plan.nodes) if node.status == TaskNodeStatus.COMPLETED),
                completed_nodes[-1],
            )
            task.result = final_node.result
            task.sources = final_node.sources
            task.assumptions = final_node.assumptions
            task.warnings = final_node.warnings
            task.updated_at = _now_iso()
            self._sync_task_deliverables(task)
            self._save_tasks()
            if failed_nodes:
                self._add_progress(
                    task_id,
                    f"Task needs review: {len(completed_nodes)} succeeded, {len(failed_nodes)} failed/skipped",
                    stage="task_review",
                )
            else:
                self._add_progress(task_id, "Task completed successfully", stage="task_complete")

            # Write episodic memory for each agent involved in this task
            try:
                agent_ids_seen: set[str] = set()
                for node in task.execution_plan.nodes:
                    if node.assigned_agent_id and node.assigned_agent_id not in agent_ids_seen:
                        agent_ids_seen.add(node.assigned_agent_id)
                        agent_cfg = factory.get_agent(node.assigned_agent_id)
                        if agent_cfg:
                            write_episode(agent_cfg, task, task.execution_plan.nodes)
            except Exception as ep_exc:
                logger.debug("Episode writing failed for task %s: %s", task_id, ep_exc)

            await self._broadcast_task(task_id, broadcast)
        except Exception as exc:
            details = _capture_failure_details(exc, failure_stage="task_execution")
            logger.exception("Task %s failed", task_id)
            task.status = TaskStatus.IN_REVIEW
            task.status_changed_at = _now_iso()
            _apply_failure_details(task, details)
            if task.execution_plan.status != TaskPlanStatus.FAILED:
                task.execution_plan.status = TaskPlanStatus.FAILED
            task.updated_at = _now_iso()
            self._sync_task_deliverables(task)
            self._save_tasks()
            self._add_progress(task_id, f"Task failed: {details.error}", stage="task_failed")
            await self._broadcast_task(task_id, broadcast)
        finally:
            await self._clear_task_agent_occupancy(task, broadcast)


def _parse_result_metadata(result_text: str) -> tuple[list[str], list[str], list[str]]:
    sources: list[str] = []
    assumptions: list[str] = []
    warnings: list[str] = []

    lines = result_text.splitlines()
    current_section: Optional[str] = None

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        if lower.startswith("##"):
            heading = lower.lstrip("#").strip()
            if "source" in heading or "référence" in heading or "reference" in heading:
                current_section = "sources"
            elif "assumption" in heading or "hypothèse" in heading or "tbd" in heading:
                current_section = "assumptions"
            elif "warning" in heading or "avertissement" in heading or "unverified" in heading:
                current_section = "warnings"
            else:
                current_section = None
        elif current_section and stripped.startswith(("-", "*", "•")) and len(stripped) > 3:
            item = stripped.lstrip("-*• ").strip()
            if current_section == "sources":
                sources.append(item)
            elif current_section == "assumptions":
                assumptions.append(item)
            elif current_section == "warnings":
                warnings.append(item)

    return sources, assumptions, warnings


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    return Orchestrator()
