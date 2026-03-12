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
from crewai import Crew, Task
from pydantic import BaseModel, Field

from app.agents.base_agent import build_crewai_agent
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
)
from app.config.token_budgets import (
    ORCHESTRATOR_DEPENDENCY_RESULT_BUDGET,
    ORCHESTRATOR_MEMORY_CTX_BUDGET,
    ORCHESTRATOR_MEMORY_RESEARCH_BUDGET,
    ORCHESTRATOR_MEMORY_SKILLS_BUDGET,
    ORCHESTRATOR_MEMORY_WORK_LEARNINGS_BUDGET,
    ORCHESTRATOR_PLANNER_MAX_TOKENS,
    ORCHESTRATOR_PLANNER_REPAIR_MAX_TOKENS,
    ORCHESTRATOR_RESULT_METADATA_MAX_TOKENS,
    ORCHESTRATOR_RESULT_METADATA_REPAIR_MAX_TOKENS,
    ORCHESTRATOR_TASK_CONTEXT_DOCS_BUDGET,
    ORCHESTRATOR_TASK_CONTEXT_PROJECT_BUDGET,
)
from app.core.agent_factory import get_agent_factory
from app.core.document_store import DocumentStore, get_document_store
from app.core.learning import run_learn_from_work
from app.core.project_brief import render_project_brief_summary
from app.core.structured_json import StructuredJsonError, request_structured_json_async
from app.core.usage_tracker import get_usage_tracker
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
from app.models.team import TeamConfig
from app.tools.registry import get_tools_for_agent

logger = logging.getLogger(__name__)

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


def _build_agent_memory_pack(cfg: AgentConfig, skills_store) -> str:
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

        work_learnings = workspace.read_skill("work_learnings")
        if work_learnings:
            parts.append(
                f"## Your reusable work learnings\n{_truncate(work_learnings, ORCHESTRATOR_MEMORY_WORK_LEARNINGS_BUDGET)}"
            )

        core_skills = workspace.read_skill("core_skills")
        if core_skills:
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


def _enrich_backstory(cfg: AgentConfig, skills_store) -> str:
    parts = [cfg.backstory]
    memory_pack = _build_agent_memory_pack(cfg, skills_store)
    if memory_pack:
        parts.append(f"\n\n## Your persistent memory\n{memory_pack}")
    if cfg.workspace_path:
        parts.append(
            f"\n\n## Your workspace\n"
            f"Directory: `{cfg.workspace_path}`\n"
            f"Use `workspace_list` to browse, `workspace_shell` to run commands, `git_clone` to clone repos."
        )
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


def _dependency_context(plan: TaskExecutionPlan, node: TaskExecutionNode) -> str:
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


def _expected_output_for_node(node: TaskExecutionNode, requires_external_research: bool) -> str:
    if node.node_type == TaskNodeType.LEAD_COMPILE:
        return (
            "A complete, well-structured deliverable that integrates all dependency outputs. "
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
            "Only use the upstream dependency outputs provided above.",
            "Preserve citations, consolidate sources, and clearly separate verified information from assumptions or TBDs.",
        ])
    else:
        base_sections.extend([
            "",
            "Stay strictly inside your scope.",
            "Do not solve the whole project. Deliver only the part that belongs to your expertise.",
            "Do not assume you have access to any other specialist's work unless it appears in the allowed dependency results section.",
        ])

    return "\n".join(base_sections) + task_suffix


def _build_task_deliverable_write_tool(task_root: Path):
    from crewai.tools import tool

    @tool("task_deliverable_write")
    def task_deliverable_write(path: str, content: str) -> str:
        """Write a deliverable file inside the current task folder.
        Use relative paths only, preferably under authored/.
        Args:
            path: Relative path such as 'authored/summary.md'
            content: File content to save
        Returns the saved relative path.
        """
        root = task_root.resolve()
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

    return task_deliverable_write


def _build_task_deliverable_list_tool(task_root: Path):
    from crewai.tools import tool

    @tool("task_deliverable_list")
    def task_deliverable_list(sub_path: str = ".") -> str:
        """List files already present inside the current task deliverables folder.
        Args:
            sub_path: Optional relative folder to inspect
        Returns a newline-separated list of files.
        """
        root = task_root.resolve()
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
            label = f"{item.relative_to(root)}"
            if item.is_dir():
                label += "/"
            entries.append(label)
        return "\n".join(entries) if entries else "No files yet."

    return task_deliverable_list


def _build_task_deliverable_read_tool(task_root: Path):
    from crewai.tools import tool

    @tool("task_deliverable_read")
    def task_deliverable_read(path: str) -> str:
        """Read a UTF-8 text deliverable file from the current task folder.
        Args:
            path: Relative file path such as 'authored/summary.md'
        Returns the file content.
        """
        root = task_root.resolve()
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

    return task_deliverable_read


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
        self._save_lock = threading.Lock()
        self._load_tasks()

    def _load_tasks(self):
        if self.tasks_file.exists():
            raw = json.loads(self.tasks_file.read_text(encoding="utf-8"))
            self._tasks = {key: TaskResponse.model_validate(value) for key, value in raw.items()}
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
            if task.status != TaskStatus.RUNNING:
                continue

            recovered_tasks += 1
            task.status = TaskStatus.FAILED
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
        task = TaskResponse(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            status=TaskStatus.PENDING,
            priority=priority,
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
        if task.status == TaskStatus.RUNNING:
            raise ValueError("Cannot delete a task while it is running.")
        del self._tasks[task_id]
        shutil.rmtree(self.task_deliverables_dir / task_id, ignore_errors=True)
        self._save_tasks()
        return True

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
        if blockers:
            has_user_fix = any(
                blocker.startswith("Plusieurs équipes") or "assign" in blocker.lower() or "disponible" in blocker.lower()
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
        specialists_text = "\n".join(
            f"- {specialist.name} (agent_id: {specialist.id}, title: {specialist.title}, specialization: {specialist.specialization})"
            for specialist in specialists
        )
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
    ) -> tuple[str, list[str], list[str], list[str]]:
        dependency_context_text = _dependency_context(plan, node)
        requires_external_research = (
            node.node_type != TaskNodeType.LEAD_COMPILE
            and _classify_task(f"{task.description}\n{node.description}") == "external_fact_task"
        )
        if requires_external_research and has_web_search(self.settings):
            os.environ["SERPER_API_KEY"] = self.settings.serper_api_key

        try:
            tools = get_tools_for_agent(
                cfg.tools,
                workspace_path=cfg.workspace_path,
                git_bindings=cfg.git_bindings,
                mcp_tool_bindings=cfg.mcp_tool_bindings,
                allow_git_write=True,
            )
            task_root = self._task_deliverables_root(task.id)
            tools.extend([
                _build_task_deliverable_write_tool(task_root),
                _build_task_deliverable_list_tool(task_root),
                _build_task_deliverable_read_tool(task_root),
            ])
            backstory = _enrich_backstory(cfg, skills_store)
            agent = build_crewai_agent(
                cfg,
                tools=tools,
                backstory_override=backstory,
                allow_delegation_override=False,
            )
            description = _prompt_for_node(
                task,
                node,
                cfg,
                task_context_pack,
                dependency_context_text,
                requires_external_research,
            )
            expected_output = _expected_output_for_node(node, requires_external_research)
        except Exception as exc:
            raise _TaskExecutionFailure(
                _format_failure_message(type(exc).__name__, str(exc)),
                error_type=type(exc).__name__,
                error_traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip(),
                failure_stage="node_setup",
            ) from exc

        crew = Crew(
            agents=[agent],
            tasks=[
                Task(
                    description=description,
                    agent=agent,
                    expected_output=expected_output,
                )
            ],
            verbose=True,
        )

        usage_tracker = get_usage_tracker()

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, crew.kickoff)
            model_name = (
                self.settings.claude_model_opus
                if cfg.model_tier == ModelTier.OPUS
                else self.settings.claude_model_sonnet
            )
            usage_tracker.log_crewai_usage(
                model_name,
                getattr(result, "token_usage", None) or getattr(crew, "usage_metrics", None),
            )
            result_text = str(result)
            sources, assumptions, warnings = await self._extract_result_metadata(
                result_text,
                task_id=task.id,
                node_id=node.id,
            )
            return result_text, sources, assumptions, warnings
        except Exception as exc:
            raise _TaskExecutionFailure(
                _format_failure_message(type(exc).__name__, str(exc)),
                error_type=type(exc).__name__,
                error_traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip(),
                failure_stage="crew_kickoff",
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

    async def execute_task(self, task_id: str, broadcast: Optional[BroadcastCallback] = None):
        task = self._tasks.get(task_id)
        if not task:
            logger.error("Task %s not found", task_id)
            return
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

        task.status = TaskStatus.RUNNING
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
                        continue

                    result_text, sources, assumptions, warnings = outcome
                    node.status = TaskNodeStatus.COMPLETED
                    node.result = result_text
                    _clear_failure_details(node)
                    node.completed_at = _now_iso()
                    node.sources = sources
                    node.assumptions = assumptions
                    node.warnings = warnings
                    self._add_progress(
                        task_id,
                        f"Node completed: {node.title}",
                        agent_id=cfg.id,
                        agent_name=cfg.name,
                        node_id=node.id,
                        stage="node_completed",
                    )

                if wave_failures:
                    task.execution_plan.status = TaskPlanStatus.FAILED
                    self._skip_remaining_nodes(task.execution_plan, "Skipped because an upstream node failed.")
                    self._sync_task_deliverables(task)
                    primary_cause = wave_failures[0].cause
                    raise _build_wave_failure(wave_failures) from primary_cause

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

            final_nodes = [node for node in task.execution_plan.nodes if node.status == TaskNodeStatus.COMPLETED]
            if not final_nodes:
                raise ValueError("No execution node completed successfully.")

            final_node = next(
                (node for node in reversed(task.execution_plan.nodes) if node.status == TaskNodeStatus.COMPLETED),
                final_nodes[-1],
            )
            task.execution_plan.status = TaskPlanStatus.COMPLETED
            task.status = TaskStatus.COMPLETED
            task.result = final_node.result
            task.sources = final_node.sources
            task.assumptions = final_node.assumptions
            task.warnings = final_node.warnings
            task.updated_at = _now_iso()
            self._sync_task_deliverables(task)
            self._save_tasks()
            self._add_progress(task_id, "Task completed successfully", stage="task_complete")
            await self._broadcast_task(task_id, broadcast)
        except Exception as exc:
            details = _capture_failure_details(exc, failure_stage="task_execution")
            logger.exception("Task %s failed", task_id)
            task.status = TaskStatus.FAILED
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
