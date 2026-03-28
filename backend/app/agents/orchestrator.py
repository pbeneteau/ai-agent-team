"""DAG orchestrator — the central execution engine for artifact production.

Ref: TDD-02 Section 3.2 (Celery task lifecycle, error handling, heartbeat),
     TDD-02 Section 5 (circuit breakers, cost enforcement),
     TDD-03 Section 13 (end-to-end execution flow — complete pseudocode),
     TDD-03 Section 12 (compilation logic),
     TDD-03 Section 8 (upstream context flow).

This module contains ``execute_dag()``, the async function invoked by the
``execute_artifact_dag`` Celery task.  It loads the execution wave, walks
through DAG waves sequentially, runs agent slots in parallel within each
wave via ``asyncio.gather``, tracks costs, handles failures, and produces
an ``ArtifactVersion`` at the end.

Lifecycle:
  LOAD → SET running → WAVE LOOP (heartbeat, parallel slots, cost check)
  → COMPILE (if needed) → FINALIZE (S3 upload, ArtifactVersion, status) → done
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.anthropic_runner import AgentResult, run_agent
from app.agents.memory import load_agent_memory
from app.agents.prompt_builder import (
    AUTO_ASSUME_RULE,
    build_system_prompt,
    build_user_message,
    get_output_format_rules,
)
from app.agents.upstream import WaveOutput, build_upstream_context
from app.config.settings import settings
from app.core.cost import compute_call_cost, increment_costs
from app.core.database import async_session_maker
from app.core.s3_workspace import upload_artifact_file
from app.models.agent import Agent
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.enums import ArtifactStatus, WaveStatus
from app.models.execution_wave import ExecutionWave
from app.models.git_provider_connection import GitProviderConnection
from app.models.project import Project
from app.models.workspace import Workspace
from app.tools.registry import (
    ExecutionContext,
    create_tool_executor,
    get_tools_for_phase,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model tier → full Anthropic model ID mapping
# ---------------------------------------------------------------------------

_MODEL_TIER_MAP: dict[str, str] = {
    "sonnet": settings.MODEL_SONNET,
    "opus": settings.MODEL_OPUS,
    "haiku": settings.MODEL_HAIKU,
}


def _resolve_model_id(model_tier: str) -> str:
    """Map an agent's model tier (e.g. ``"sonnet"``) to the full model ID."""
    return _MODEL_TIER_MAP.get(model_tier, settings.MODEL_SONNET)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BudgetExceededError(Exception):
    """Raised when execution cost exceeds the artifact or workspace budget."""


class SlotExecutionError(Exception):
    """Raised when an agent slot fails during execution."""

    def __init__(self, slot_key: str, message: str) -> None:
        super().__init__(f"Slot '{slot_key}' failed: {message}")
        self.slot_key = slot_key


# ---------------------------------------------------------------------------
# Data types — plain value objects passed between orchestrator functions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ArtifactCtx:
    """Immutable snapshot of artifact fields needed during execution."""

    id: str
    project_id: str
    workspace_id: str
    title: str
    goal: str | None
    target_audience: str | None
    context: str | None
    description: str | None
    artifact_type: str
    max_budget_usd: Decimal
    total_cost_usd: Decimal
    current_version: int


@dataclass(frozen=True, slots=True)
class _ProjectCtx:
    """Immutable snapshot of project fields needed during execution."""

    id: str
    brief_published: str | None


@dataclass(frozen=True, slots=True)
class SlotResult:
    """Output from a single slot's agent execution."""

    output_key: str
    agent_name: str
    slot_label: str
    text: str
    files: dict[str, str]
    input_tokens: int
    output_tokens: int
    cost: Decimal
    assumptions: list[str]
    sources: list[str]


# ---------------------------------------------------------------------------
# Compile prompt (TDD-03 Section 12.3 — verbatim)
# ---------------------------------------------------------------------------

_COMPILE_SYSTEM_PROMPT: str = """\
You are a Compiler agent. Your job is to merge outputs from multiple \
agents into a single, coherent deliverable."""

_COMPILE_TASK: str = """\
## Your Task
You are the Compiler. Multiple agents have produced outputs in parallel.
Your job is to merge them into a single, coherent deliverable.

Rules:
- Preserve all citations and sources from upstream outputs.
- Resolve any contradictions between upstream outputs (prefer the more specific
  or better-sourced claim).
- Maintain a consistent voice and structure throughout.
- Do NOT add new information — only organize and merge what was produced.
- Output the final deliverable in its entirety."""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def execute_dag(execution_wave_id: str) -> None:
    """Execute a full DAG producing one ArtifactVersion.

    This is the async function called by the ``execute_artifact_dag`` Celery
    task.  It owns the entire lifecycle from loading the wave through to
    creating the final ``ArtifactVersion`` row.

    Args:
        execution_wave_id: Primary key of the ``ExecutionWave`` row to execute.

    Raises:
        BudgetExceededError: If running cost exceeds the artifact budget.
        SlotExecutionError: If any agent slot fails.
    """
    async with async_session_maker() as db:
        # ----------------------------------------------------------------
        # 1. LOAD — wave, artifact, project, workspace
        # ----------------------------------------------------------------
        wave = await db.get(ExecutionWave, execution_wave_id)
        if wave is None:
            raise ValueError(
                f"ExecutionWave '{execution_wave_id}' not found"
            )

        artifact = await db.get(Artifact, wave.artifact_id)
        if artifact is None:
            raise ValueError(
                f"Artifact '{wave.artifact_id}' not found"
            )

        project = await db.get(Project, artifact.project_id)
        if project is None:
            raise ValueError(
                f"Project '{artifact.project_id}' not found"
            )

        # Resolve workspace_id by querying the project's parent.
        workspace_result = await db.execute(
            select(Workspace.id).where(
                Workspace.id == (
                    select(Project.workspace_id)
                    .where(Project.id == project.id)
                    .scalar_subquery()
                )
            )
        )
        workspace_id: str = workspace_result.scalar_one()

        # Snapshot artifact/project fields so concurrent slot sessions
        # don't need to access ORM objects from this session.
        artifact_ctx = _ArtifactCtx(
            id=artifact.id,
            project_id=project.id,
            workspace_id=workspace_id,
            title=artifact.title,
            goal=artifact.goal,
            target_audience=artifact.target_audience,
            context=artifact.context,
            description=artifact.description,
            artifact_type=artifact.artifact_type,
            max_budget_usd=Decimal(str(artifact.max_budget_usd)),
            total_cost_usd=Decimal(str(artifact.total_cost_usd)),
            current_version=artifact.current_version,
        )
        project_ctx = _ProjectCtx(
            id=project.id,
            brief_published=project.brief_published,
        )

        dag_plan: dict[str, Any] = wave.dag_plan
        waves_data: list[dict[str, Any]] = dag_plan["waves"]
        total_steps = len(waves_data)

        # ----------------------------------------------------------------
        # 2. SET status = running
        # ----------------------------------------------------------------
        wave.status = WaveStatus.RUNNING.value
        wave.started_at = datetime.now(timezone.utc)
        wave.total_steps = total_steps
        await db.commit()

        logger.info(
            "Starting DAG execution: wave=%s artifact=%s waves=%d",
            execution_wave_id, artifact_ctx.id, total_steps,
        )

        try:
            wave_outputs: dict[str, WaveOutput] = {}
            running_cost = Decimal("0")
            running_input_tokens: int = 0
            running_output_tokens: int = 0
            all_assumptions: list[str] = []
            all_sources: list[str] = []
            all_files: dict[str, str] = {}

            # --------------------------------------------------------
            # 3. WAVE LOOP — sequential waves, parallel slots
            # --------------------------------------------------------
            for wave_data in waves_data:
                wave_number: int = wave_data["wave_number"]
                wave_label: str = wave_data["label"]
                agents_in_wave: list[dict[str, Any]] = wave_data["agents"]

                logger.info(
                    "Wave %d/%d: %s (%d slots)",
                    wave_number, total_steps, wave_label, len(agents_in_wave),
                )

                # 3a. Update heartbeat — committed immediately for frontend poll
                wave.current_step = wave_number
                await db.commit()

                # 3b. Pre-wave budget check
                projected_total = artifact_ctx.total_cost_usd + running_cost
                if projected_total > artifact_ctx.max_budget_usd:
                    raise BudgetExceededError(
                        f"Budget exceeded before wave {wave_number}: "
                        f"${projected_total} > ${artifact_ctx.max_budget_usd}"
                    )

                # 3c. Execute all slots in this wave concurrently
                slot_coros = [
                    _execute_slot(
                        slot_data=agent_data,
                        wave_outputs=wave_outputs,
                        artifact_ctx=artifact_ctx,
                        project_ctx=project_ctx,
                    )
                    for agent_data in agents_in_wave
                ]
                results = await asyncio.gather(
                    *slot_coros, return_exceptions=True
                )

                # 3d. Check for slot failures
                slot_results: list[SlotResult] = []
                for i, result in enumerate(results):
                    if isinstance(result, BaseException):
                        failed_key = agents_in_wave[i].get(
                            "output_key", f"slot_{i}"
                        )
                        logger.error(
                            "Slot '%s' in wave %d failed: %s",
                            failed_key, wave_number, result,
                            exc_info=result,
                        )
                        raise SlotExecutionError(
                            slot_key=failed_key,
                            message=str(result),
                        ) from result
                    slot_results.append(result)

                # 3e. Accumulate outputs into wave_outputs dict
                wave_slot_cost = Decimal("0")
                wave_slot_input = 0
                wave_slot_output = 0

                for sr in slot_results:
                    wave_outputs[sr.output_key] = WaveOutput(
                        text=sr.text,
                        agent_name=sr.agent_name,
                        slot_label=sr.slot_label,
                        files=list(sr.files.keys()),
                    )
                    wave_slot_cost += sr.cost
                    wave_slot_input += sr.input_tokens
                    wave_slot_output += sr.output_tokens
                    all_assumptions.extend(sr.assumptions)
                    all_sources.extend(sr.sources)
                    # Later wave wins on file path conflict (TDD-03 8.3)
                    all_files.update(sr.files)

                running_cost += wave_slot_cost
                running_input_tokens += wave_slot_input
                running_output_tokens += wave_slot_output

                # 3f. Increment costs atomically in DB
                await increment_costs(
                    db=db,
                    execution_wave_id=execution_wave_id,
                    artifact_id=artifact_ctx.id,
                    workspace_id=workspace_id,
                    cost=wave_slot_cost,
                    input_tokens=wave_slot_input,
                    output_tokens=wave_slot_output,
                )

                # 3g. Update heartbeat with running cost — commit immediately
                wave.cost_usd = float(running_cost)
                wave.input_tokens = running_input_tokens
                wave.output_tokens = running_output_tokens
                await db.commit()

                # 3h. Post-wave budget check (TDD-02 Section 5.3 step 5)
                post_wave_total = artifact_ctx.total_cost_usd + running_cost
                if post_wave_total > artifact_ctx.max_budget_usd:
                    raise BudgetExceededError(
                        f"Budget exceeded after wave {wave_number}: "
                        f"${post_wave_total} > ${artifact_ctx.max_budget_usd}"
                    )

                logger.info(
                    "Wave %d/%d completed: cost=$%.4f tokens=%d/%d",
                    wave_number, total_steps,
                    wave_slot_cost, wave_slot_input, wave_slot_output,
                )

                # Broadcast wave completion
                await _broadcast_safe(
                    "execution.wave_completed",
                    {
                        "artifact_id": artifact_ctx.id,
                        "wave_number": wave_number,
                        "total_waves": total_steps,
                    },
                )

                # Check for budget warning (>= 90%)
                await _check_budget_warning(db, workspace_id)

            # --------------------------------------------------------
            # 4. COMPILE — if template requires merging parallel outputs
            # --------------------------------------------------------
            needs_compile: bool = dag_plan.get("needs_compile", False)
            if needs_compile:
                logger.info("Running compilation step")
                compile_result = await _execute_compile(
                    wave_outputs=wave_outputs,
                    artifact_ctx=artifact_ctx,
                    project_ctx=project_ctx,
                )
                # Merge compile output — compiler output wins
                all_files.update(compile_result.files)
                if compile_result.text:
                    # Overwrite all_files with compile output if it wrote files;
                    # if it produced text only, store as the main output file.
                    if not compile_result.files:
                        all_files["output.md"] = compile_result.text

                running_cost += compile_result.cost
                running_input_tokens += compile_result.input_tokens
                running_output_tokens += compile_result.output_tokens
                all_assumptions.extend(compile_result.assumptions)
                all_sources.extend(compile_result.sources)

                # Increment compile cost
                await increment_costs(
                    db=db,
                    execution_wave_id=execution_wave_id,
                    artifact_id=artifact_ctx.id,
                    workspace_id=workspace_id,
                    cost=compile_result.cost,
                    input_tokens=compile_result.input_tokens,
                    output_tokens=compile_result.output_tokens,
                )
                wave.cost_usd = float(running_cost)
                wave.input_tokens = running_input_tokens
                wave.output_tokens = running_output_tokens
                await db.commit()

            # If no files were produced via file_write, store the last
            # wave's text output as the primary deliverable file.
            if not all_files:
                last_wave_agents = waves_data[-1]["agents"]
                last_keys = [a["output_key"] for a in last_wave_agents]
                for key in last_keys:
                    wo = wave_outputs.get(key)
                    if wo and wo.text:
                        ext = (
                            "md" if artifact_ctx.artifact_type == "prose"
                            else "txt"
                        )
                        all_files[f"{key}.{ext}"] = wo.text

            # --------------------------------------------------------
            # 5. FINALIZE — S3 upload, ArtifactVersion, status updates
            # --------------------------------------------------------
            version_number = artifact_ctx.current_version + 1
            s3_prefix = (
                f"artifacts/{artifact_ctx.id}/v{version_number}/"
            )

            # Upload files to S3
            file_manifest: list[dict[str, Any]] = []
            for file_path, content in sorted(all_files.items()):
                content_bytes = content.encode("utf-8")
                upload_artifact_file(
                    artifact_id=artifact_ctx.id,
                    version_number=version_number,
                    file_path=file_path,
                    content=content_bytes,
                )
                file_manifest.append({
                    "path": file_path,
                    "size_bytes": len(content_bytes),
                    "content_type": _guess_content_type(file_path),
                })

            logger.info(
                "Uploaded %d files to S3 prefix '%s'",
                len(file_manifest), s3_prefix,
            )

            # Deduplicate sources
            unique_sources = list(dict.fromkeys(all_sources))

            # Create ArtifactVersion row
            version = ArtifactVersion(
                id=str(uuid.uuid4()),
                artifact_id=artifact_ctx.id,
                version_number=version_number,
                s3_prefix=s3_prefix,
                file_manifest=file_manifest,
                token_cost_usd=float(running_cost),
                input_tokens=running_input_tokens,
                output_tokens=running_output_tokens,
                assumptions=all_assumptions,
                sources=unique_sources,
                execution_wave_id=execution_wave_id,
            )
            db.add(version)

            # Update artifact: status → in_review, bump version
            await db.execute(
                update(Artifact)
                .where(Artifact.id == artifact_ctx.id)
                .values(
                    status=ArtifactStatus.IN_REVIEW.value,
                    current_version=version_number,
                )
            )

            # Update wave: status → completed
            wave.status = WaveStatus.COMPLETED.value
            wave.completed_at = datetime.now(timezone.utc)
            wave.cost_usd = float(running_cost)
            wave.input_tokens = running_input_tokens
            wave.output_tokens = running_output_tokens

            await db.commit()

            logger.info(
                "DAG execution completed: wave=%s version=v%d "
                "cost=$%.4f files=%d",
                execution_wave_id, version_number,
                running_cost, len(file_manifest),
            )

            # Broadcast artifact status change
            await _broadcast_safe(
                "artifact.status_changed",
                {
                    "artifact_id": artifact_ctx.id,
                    "status": ArtifactStatus.IN_REVIEW.value,
                    "project_id": artifact_ctx.project_id,
                },
            )

            # --------------------------------------------------------
            # 6. GIT PUSH — for code artifacts with git_repo_url
            # --------------------------------------------------------
            if artifact_ctx.artifact_type == "code":
                await _try_git_push(
                    db=db,
                    artifact_id=artifact_ctx.id,
                    workspace_id=workspace_id,
                    version_number=version_number,
                    file_manifest=file_manifest,
                    is_iteration=(wave.trigger == "iteration"),
                )

        except BudgetExceededError as exc:
            logger.warning("Budget exceeded: %s", exc)
            wave.status = WaveStatus.FAILED.value
            wave.error_message = "budget_exceeded"
            wave.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await _broadcast_safe(
                "execution.failed",
                {"artifact_id": artifact_ctx.id, "error_message": "budget_exceeded"},
            )
            raise

        except (SlotExecutionError, Exception) as exc:
            logger.error(
                "DAG execution failed: wave=%s error=%s",
                execution_wave_id, exc,
                exc_info=True,
            )
            wave.status = WaveStatus.FAILED.value
            wave.error_message = str(exc)[:2000]
            wave.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await _broadcast_safe(
                "execution.failed",
                {"artifact_id": artifact_ctx.id, "error_message": str(exc)[:200]},
            )
            raise


# ---------------------------------------------------------------------------
# Slot execution — runs a single agent within a wave
# ---------------------------------------------------------------------------


async def _execute_slot(
    slot_data: dict[str, Any],
    wave_outputs: dict[str, WaveOutput],
    artifact_ctx: _ArtifactCtx,
    project_ctx: _ProjectCtx,
) -> SlotResult:
    """Execute a single DAG slot: load agent → build prompt → run agent.

    Each slot gets its own DB session to avoid concurrency issues when
    multiple slots run in parallel via ``asyncio.gather``.

    Args:
        slot_data: One entry from ``dag_plan["waves"][n]["agents"]``.
        wave_outputs: Accumulated outputs from all previous waves.
        artifact_ctx: Immutable artifact field snapshot.
        project_ctx: Immutable project field snapshot.

    Returns:
        ``SlotResult`` with agent output, files, tokens, cost.

    Raises:
        SlotExecutionError: If the agent cannot be found or the loop fails.
    """
    agent_id: str | None = slot_data.get("agent_id")
    role_in_wave: str = slot_data["role_in_wave"]
    output_key: str = slot_data["output_key"]
    depends_on: list[str] = slot_data.get("depends_on", [])

    if agent_id is None:
        raise SlotExecutionError(
            slot_key=output_key,
            message="No agent_id assigned to slot",
        )

    async with async_session_maker() as db:
        # Load agent from DB
        agent = await db.get(Agent, agent_id)
        if agent is None:
            raise SlotExecutionError(
                slot_key=output_key,
                message=f"Agent '{agent_id}' not found",
            )

        agent_name: str = agent.name
        model_tier: str = agent.model_tier

        # Load agent memory (skills + work learnings)
        agent_memory: str = await load_agent_memory(agent_id, db)

        # Build upstream context from depends_on
        slot_deps = SimpleNamespace(depends_on=depends_on)
        upstream_context: str | None = build_upstream_context(
            slot_deps, wave_outputs
        )

        # Build output format rules
        output_format_rules: str = get_output_format_rules(
            artifact_ctx.artifact_type, output_key
        )

        # Build system prompt (positions 1-3)
        system_prompt: str = build_system_prompt(agent, output_format_rules)

        # Build user message (positions 4-9)
        artifact_brief: dict[str, str | None] = {
            "title": artifact_ctx.title,
            "goal": artifact_ctx.goal,
            "target_audience": artifact_ctx.target_audience,
            "context": artifact_ctx.context,
            "description": artifact_ctx.description,
        }
        user_message: str = build_user_message(
            agent_memory=agent_memory or None,
            upstream_context=upstream_context,
            project_brief=project_ctx.brief_published,
            artifact_brief=artifact_brief,
            wave_task=role_in_wave,
        )

        # Get tools for execution phase
        tools = get_tools_for_phase("execution")

        # Create execution context for tool dispatch
        exec_context = ExecutionContext(
            project_id=project_ctx.id,
            db_session=db,
        )
        tool_executor = create_tool_executor(tools, exec_context)

        # Resolve model ID
        model_id: str = _resolve_model_id(model_tier)

        logger.debug(
            "Running slot '%s' with agent '%s' (%s)",
            output_key, agent_name, model_id,
        )

        # Run the agent loop (TDD-03 Section 6.4)
        result: AgentResult = await run_agent(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
            model=model_id,
            tool_executor=tool_executor,
        )

        # Compute cost for this slot
        cost: Decimal = compute_call_cost(
            result.input_tokens, result.output_tokens, model_tier
        )

        logger.debug(
            "Slot '%s' completed: tokens=%d/%d cost=$%.4f files=%d",
            output_key, result.input_tokens, result.output_tokens,
            cost, len(result.files),
        )

        return SlotResult(
            output_key=output_key,
            agent_name=agent_name,
            slot_label=role_in_wave,
            text=result.text,
            files=result.files,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost=cost,
            assumptions=result.assumptions,
            sources=result.sources,
        )


# ---------------------------------------------------------------------------
# Compilation — merges parallel outputs when template requires it
# ---------------------------------------------------------------------------


async def _execute_compile(
    wave_outputs: dict[str, WaveOutput],
    artifact_ctx: _ArtifactCtx,
    project_ctx: _ProjectCtx,
) -> SlotResult:
    """Run the compilation step to merge all upstream outputs.

    Ref: TDD-03 Section 12.

    Uses Sonnet as the compiler model.  Builds upstream context from ALL
    wave outputs (not just the last wave), then runs the compile agent
    with the standard compile prompt.

    Args:
        wave_outputs: All slot outputs from all waves in the DAG.
        artifact_ctx: Artifact field snapshot.
        project_ctx: Project field snapshot.

    Returns:
        ``SlotResult`` containing the merged output.
    """
    # Build upstream context from all outputs
    all_keys = list(wave_outputs.keys())
    compile_deps = SimpleNamespace(depends_on=all_keys)
    upstream_context: str | None = build_upstream_context(
        compile_deps, wave_outputs
    )

    # Build artifact brief
    artifact_brief: dict[str, str | None] = {
        "title": artifact_ctx.title,
        "goal": artifact_ctx.goal,
        "target_audience": artifact_ctx.target_audience,
        "context": artifact_ctx.context,
        "description": artifact_ctx.description,
    }

    # Compile prompt uses a fixed system prompt + the compile task
    output_format_rules = get_output_format_rules(
        artifact_ctx.artifact_type, "compiler"
    )
    system_prompt = (
        f"{_COMPILE_SYSTEM_PROMPT}\n\n{AUTO_ASSUME_RULE}\n\n{output_format_rules}"
    )

    user_message: str = build_user_message(
        agent_memory=None,
        upstream_context=upstream_context,
        project_brief=project_ctx.brief_published,
        artifact_brief=artifact_brief,
        wave_task=_COMPILE_TASK,
    )

    # Tools: file tools only for compilation
    tools = get_tools_for_phase("execution")
    exec_context = ExecutionContext(project_id=project_ctx.id)
    tool_executor = create_tool_executor(tools, exec_context)

    model_id: str = _resolve_model_id("sonnet")

    result: AgentResult = await run_agent(
        system_prompt=system_prompt,
        user_message=user_message,
        tools=tools,
        model=model_id,
        tool_executor=tool_executor,
    )

    cost: Decimal = compute_call_cost(
        result.input_tokens, result.output_tokens, "sonnet"
    )

    return SlotResult(
        output_key="_compile",
        agent_name="Compiler",
        slot_label="Compilation",
        text=result.text,
        files=result.files,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost=cost,
        assumptions=result.assumptions,
        sources=result.sources,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _guess_content_type(file_path: str) -> str:
    """Guess MIME type from file extension for the file manifest."""
    import mimetypes
    content_type, _ = mimetypes.guess_type(file_path)
    return content_type or "application/octet-stream"


async def _try_git_push(
    db: AsyncSession,
    artifact_id: str,
    workspace_id: str,
    version_number: int,
    file_manifest: list[dict[str, Any]],
    is_iteration: bool,
) -> None:
    """Best-effort git push after DAG finalization for code artifacts.

    Does not raise — git push failures are logged but do not fail the execution.
    """
    try:
        from app.core.git_push import push_artifact_to_git, push_iteration_to_git

        # Reload artifact and connections within the existing session
        artifact = await db.get(Artifact, artifact_id)
        if artifact is None or not artifact.git_repo_url:
            return

        result = await db.execute(
            select(GitProviderConnection).where(
                GitProviderConnection.workspace_id == workspace_id,
                GitProviderConnection.status == "active",
            )
        )
        connections = list(result.scalars().all())
        if not connections:
            logger.info("No active git connections for workspace %s", workspace_id)
            return

        if is_iteration and artifact.git_feature_branch:
            await push_iteration_to_git(
                artifact=artifact,
                version_number=version_number,
                file_manifest=file_manifest,
                connections=connections,
            )
        else:
            await push_artifact_to_git(
                artifact=artifact,
                version_number=version_number,
                file_manifest=file_manifest,
                connections=connections,
                db=db,
            )
    except Exception:
        logger.exception(
            "Git push failed (non-fatal) for artifact %s", artifact_id
        )


async def _broadcast_safe(event_type: str, payload: dict[str, Any]) -> None:
    """Best-effort WebSocket broadcast — never raises."""
    try:
        from app.api.websocket_manager import broadcast_event
        await broadcast_event(event_type, payload)
    except Exception:
        logger.debug("WebSocket broadcast failed (non-fatal): %s", event_type)


async def _check_budget_warning(db: AsyncSession, workspace_id: str) -> None:
    """Broadcast budget.warning if usage >= 90%."""
    try:
        workspace = await db.get(Workspace, workspace_id)
        if workspace is None:
            return
        monthly_budget = float(workspace.monthly_budget_usd)
        monthly_spent = float(workspace.monthly_spend_usd)
        if monthly_budget <= 0:
            return
        usage_pct = int(monthly_spent / monthly_budget * 100)
        if usage_pct >= 90:
            remaining = max(0.0, monthly_budget - monthly_spent)
            await _broadcast_safe(
                "budget.warning",
                {"usage_pct": usage_pct, "remaining_usd": round(remaining, 2)},
            )
    except Exception:
        logger.debug("Budget warning check failed (non-fatal)")
