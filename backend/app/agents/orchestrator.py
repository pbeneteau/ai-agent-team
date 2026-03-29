"""DAG orchestrator — lead-guided execution engine for artifact production.

Execution flow for lead-structured templates:

  Phase 1 — Planning (once):
    Lead agents receive the brief, research context, and produce a structured
    delegation plan. Each lead outputs a "## Specialist Delegation" section
    with per-specialist task briefs.

  Phase 2 — Execution + Review loop (up to max_iterations):
    a) Execution waves: specialist agents run with their delegated tasks
       injected as role context. On revise iterations, review feedback is
       also injected.
    b) Review wave: lead agents evaluate all outputs and output one of:
         APPROVE   → finalize immediately
         MINOR_FIX → lead applies small corrections directly (file_write),
                     then finalize
         REVISE    → extract per-specialist feedback, re-run execution waves

  Fallback: if max_iterations is reached, the last execution output is
  finalized regardless of review decision.

Legacy templates (no wave_type field) run the original flat wave loop.
"""

from __future__ import annotations

import asyncio
import logging
import re
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
    build_review_criteria_block,
    build_system_prompt,
    build_user_message,
    get_output_format_rules,
)
from app.agents.upstream import WaveOutput, build_upstream_context
from app.config.settings import settings
from app.core.cost import compute_call_cost, increment_costs
from app.core.database import async_session_maker, engine
from app.core.s3_workspace import upload_artifact_file
from app.models.agent import Agent
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.enums import ArtifactStatus, WaveStatus
from app.models.execution_wave import ExecutionWave
from app.models.git_provider_connection import GitProviderConnection
from app.models.project import Project
from app.models.workspace import Workspace
from app.agents.telemetry import (
    ExecutionMetrics,
    ReviewLoopMetrics,
    Timer,
    emit_execution_metrics,
    emit_review_loop_metrics,
)
from app.tools.registry import (
    ExecutionContext,
    Phase,
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
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ArtifactCtx:
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
    id: str
    brief_published: str | None


@dataclass(frozen=True, slots=True)
class SlotResult:
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
# Compile prompt (unchanged from original)
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
# Minor-fix system prompt
# ---------------------------------------------------------------------------

_MINOR_FIX_SYSTEM_PROMPT: str = """\
You are a lead engineer performing a minor fix pass. You have already reviewed
the work and identified small issues you can correct directly. Use file_read to
examine relevant files and file_write to apply your corrections. Fix precisely
what you identified — do not rewrite everything."""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def execute_dag(execution_wave_id: str) -> None:
    """Execute a full DAG producing one ArtifactVersion."""
    async with async_session_maker() as db:
        # ----------------------------------------------------------------
        # 1. LOAD
        # ----------------------------------------------------------------
        wave = await db.get(ExecutionWave, execution_wave_id)
        if wave is None:
            raise ValueError(f"ExecutionWave '{execution_wave_id}' not found")

        artifact = await db.get(Artifact, wave.artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact '{wave.artifact_id}' not found")

        project = await db.get(Project, artifact.project_id)
        if project is None:
            raise ValueError(f"Project '{artifact.project_id}' not found")

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
            "Starting DAG: wave=%s artifact=%s waves=%d",
            execution_wave_id, artifact_ctx.id, total_steps,
        )

        try:
            # Detect lead-structured vs legacy template
            has_lead_structure = any(
                w.get("wave_type") in ("planning", "review")
                for w in waves_data
            )

            if has_lead_structure:
                all_files, running_cost, running_input_tokens, running_output_tokens, \
                    all_assumptions, all_sources = await _execute_lead_dag(
                        dag_plan=dag_plan,
                        wave=wave,
                        artifact_ctx=artifact_ctx,
                        project_ctx=project_ctx,
                        workspace_id=workspace_id,
                        execution_wave_id=execution_wave_id,
                        db=db,
                    )
            else:
                all_files, running_cost, running_input_tokens, running_output_tokens, \
                    all_assumptions, all_sources = await _execute_legacy_dag(
                        dag_plan=dag_plan,
                        wave=wave,
                        artifact_ctx=artifact_ctx,
                        project_ctx=project_ctx,
                        workspace_id=workspace_id,
                        execution_wave_id=execution_wave_id,
                        db=db,
                    )

            # --------------------------------------------------------
            # FINALIZE — S3 upload, ArtifactVersion, status
            # --------------------------------------------------------
            version_number = artifact_ctx.current_version + 1
            s3_prefix = f"artifacts/{artifact_ctx.id}/v{version_number}/"

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

            unique_sources = list(dict.fromkeys(all_sources))

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

            await db.execute(
                update(Artifact)
                .where(Artifact.id == artifact_ctx.id)
                .values(
                    status=ArtifactStatus.IN_REVIEW.value,
                    current_version=version_number,
                )
            )

            wave.status = WaveStatus.COMPLETED.value
            wave.completed_at = datetime.now(timezone.utc)
            wave.cost_usd = float(running_cost)
            wave.input_tokens = running_input_tokens
            wave.output_tokens = running_output_tokens
            await db.commit()

            logger.info(
                "DAG completed: wave=%s version=v%d cost=$%.4f files=%d",
                execution_wave_id, version_number, running_cost, len(file_manifest),
            )

            await _broadcast_safe(
                "artifact.status_changed",
                {
                    "artifact_id": artifact_ctx.id,
                    "status": ArtifactStatus.IN_REVIEW.value,
                    "project_id": artifact_ctx.project_id,
                },
            )

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
            logger.error("DAG failed: wave=%s error=%s", execution_wave_id, exc, exc_info=True)
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
# Lead-guided execution
# ---------------------------------------------------------------------------


async def _execute_lead_dag(
    dag_plan: dict[str, Any],
    wave: ExecutionWave,
    artifact_ctx: _ArtifactCtx,
    project_ctx: _ProjectCtx,
    workspace_id: str,
    execution_wave_id: str,
    db: AsyncSession,
) -> tuple[dict[str, str], Decimal, int, int, list[str], list[str]]:
    """Execute a lead-structured DAG.

    Returns: (all_files, cost, input_tokens, output_tokens, assumptions, sources)
    """
    waves_data = dag_plan["waves"]
    max_iterations: int = dag_plan.get("max_iterations", 3)

    # Load template metadata (Tickets 17.2, 17.3)
    review_criteria: tuple[str, ...] = ()
    validation_wave_def: Any = None  # DagWave | None
    template_id: str | None = dag_plan.get("template_id")
    if template_id:
        try:
            from app.agents.dag_templates import get_template
            _template = get_template(template_id)
            review_criteria = _template.review_criteria
            validation_wave_def = _template.validation_wave
        except KeyError:
            pass  # Unknown template — no criteria or validation

    planning_waves = [w for w in waves_data if w.get("wave_type") == "planning"]
    execution_waves = [w for w in waves_data if w.get("wave_type") == "execution"]
    review_wave_data = next((w for w in waves_data if w.get("wave_type") == "review"), None)

    running_cost = Decimal("0")
    running_input_tokens = 0
    running_output_tokens = 0
    all_assumptions: list[str] = []
    all_sources: list[str] = []

    # ------------------------------------------------------------------
    # Phase 1: Planning waves (run once — preserved across iterations)
    # ------------------------------------------------------------------
    planning_outputs: dict[str, WaveOutput] = {}
    planning_files: dict[str, str] = {}

    for wave_data in planning_waves:
        wave.current_step = wave_data["wave_number"]
        await db.commit()

        _check_budget(artifact_ctx, running_cost, wave_data["wave_number"])

        slot_results = await _run_wave_parallel(
            wave_data=wave_data,
            wave_outputs=planning_outputs,
            artifact_ctx=artifact_ctx,
            project_ctx=project_ctx,
            phase="planning",
        )

        wave_cost = Decimal("0")
        for sr in slot_results:
            planning_outputs[sr.output_key] = WaveOutput(
                text=sr.text,
                agent_name=sr.agent_name,
                slot_label=sr.slot_label,
                files=list(sr.files.keys()),
            )
            planning_files.update(sr.files)
            wave_cost += sr.cost
            running_input_tokens += sr.input_tokens
            running_output_tokens += sr.output_tokens
            all_assumptions.extend(sr.assumptions)
            all_sources.extend(sr.sources)

        running_cost += wave_cost
        await increment_costs(
            db=db,
            execution_wave_id=execution_wave_id,
            artifact_id=artifact_ctx.id,
            workspace_id=workspace_id,
            cost=wave_cost,
            input_tokens=sum(sr.input_tokens for sr in slot_results),
            output_tokens=sum(sr.output_tokens for sr in slot_results),
        )
        wave.cost_usd = float(running_cost)
        wave.input_tokens = running_input_tokens
        wave.output_tokens = running_output_tokens
        await db.commit()

        await _broadcast_safe(
            "execution.wave_completed",
            {
                "artifact_id": artifact_ctx.id,
                "wave_number": wave_data["wave_number"],
                "total_waves": len(waves_data),
            },
        )

    # Extract delegation plan from planning outputs
    delegation_plan = _extract_delegation_plan(planning_outputs, execution_waves)
    logger.info(
        "Delegation plan extracted: %d slots mapped", len(delegation_plan)
    )

    # ------------------------------------------------------------------
    # Phase 1.5: Delegation validation (Ticket 17.3, AD-27)
    # ------------------------------------------------------------------
    if validation_wave_def is not None:
        delegation_plan, planning_outputs, planning_files, \
            running_cost, running_input_tokens, running_output_tokens = \
            await _run_delegation_validation(
                validation_wave_def=validation_wave_def,
                planning_outputs=planning_outputs,
                planning_files=planning_files,
                planning_waves=planning_waves,
                execution_waves=execution_waves,
                wave=wave,
                artifact_ctx=artifact_ctx,
                project_ctx=project_ctx,
                workspace_id=workspace_id,
                execution_wave_id=execution_wave_id,
                delegation_plan=delegation_plan,
                running_cost=running_cost,
                running_input_tokens=running_input_tokens,
                running_output_tokens=running_output_tokens,
                all_assumptions=all_assumptions,
                all_sources=all_sources,
                waves_data=waves_data,
                db=db,
            )

    # ------------------------------------------------------------------
    # Phase 2: Execution + Review loop
    # ------------------------------------------------------------------
    review_feedback: dict[str, str] = {}
    final_files: dict[str, str] = dict(planning_files)

    for iteration in range(max_iterations + 1):
        review_timer = Timer()
        is_forced = (iteration == max_iterations)
        if is_forced:
            logger.warning(
                "Max iterations (%d) reached for wave=%s — force-finalizing",
                max_iterations, execution_wave_id,
            )

        # ------ Execution waves ------
        iteration_outputs: dict[str, WaveOutput] = dict(planning_outputs)
        iteration_files: dict[str, str] = dict(planning_files)

        for wave_data in execution_waves:
            wave.current_step = wave_data["wave_number"]
            await db.commit()

            _check_budget(artifact_ctx, running_cost, wave_data["wave_number"])

            slot_results = await _run_wave_parallel(
                wave_data=wave_data,
                wave_outputs=iteration_outputs,
                artifact_ctx=artifact_ctx,
                project_ctx=project_ctx,
                phase="execution",
                delegation_plan=delegation_plan,
                review_feedback=review_feedback,
            )

            wave_cost = Decimal("0")
            for sr in slot_results:
                iteration_outputs[sr.output_key] = WaveOutput(
                    text=sr.text,
                    agent_name=sr.agent_name,
                    slot_label=sr.slot_label,
                    files=list(sr.files.keys()),
                )
                iteration_files.update(sr.files)
                wave_cost += sr.cost
                running_input_tokens += sr.input_tokens
                running_output_tokens += sr.output_tokens
                all_assumptions.extend(sr.assumptions)
                all_sources.extend(sr.sources)

            running_cost += wave_cost
            await increment_costs(
                db=db,
                execution_wave_id=execution_wave_id,
                artifact_id=artifact_ctx.id,
                workspace_id=workspace_id,
                cost=wave_cost,
                input_tokens=sum(sr.input_tokens for sr in slot_results),
                output_tokens=sum(sr.output_tokens for sr in slot_results),
            )
            wave.cost_usd = float(running_cost)
            wave.input_tokens = running_input_tokens
            wave.output_tokens = running_output_tokens
            await db.commit()

            await _broadcast_safe(
                "execution.wave_completed",
                {
                    "artifact_id": artifact_ctx.id,
                    "wave_number": wave_data["wave_number"],
                    "total_waves": len(waves_data),
                },
            )

        # Ensure files produced
        if not iteration_files:
            iteration_files = _text_outputs_to_files(
                iteration_outputs, execution_waves, artifact_ctx.artifact_type
            )

        # ------ Review wave ------
        if review_wave_data is None or is_forced:
            final_files = iteration_files
            break

        wave.current_step = review_wave_data["wave_number"]
        await db.commit()

        _check_budget(artifact_ctx, running_cost, review_wave_data["wave_number"])

        review_timer.__enter__()

        review_results = await _run_wave_parallel(
            wave_data=review_wave_data,
            wave_outputs=iteration_outputs,
            artifact_ctx=artifact_ctx,
            project_ctx=project_ctx,
            phase="review",
            shared_files=iteration_files,
            review_criteria=review_criteria,
        )

        wave_cost = Decimal("0")
        for sr in review_results:
            iteration_outputs[sr.output_key] = WaveOutput(
                text=sr.text,
                agent_name=sr.agent_name,
                slot_label=sr.slot_label,
                files=list(sr.files.keys()),
            )
            wave_cost += sr.cost
            running_input_tokens += sr.input_tokens
            running_output_tokens += sr.output_tokens
            all_assumptions.extend(sr.assumptions)

        running_cost += wave_cost
        await increment_costs(
            db=db,
            execution_wave_id=execution_wave_id,
            artifact_id=artifact_ctx.id,
            workspace_id=workspace_id,
            cost=wave_cost,
            input_tokens=sum(sr.input_tokens for sr in review_results),
            output_tokens=sum(sr.output_tokens for sr in review_results),
        )
        wave.cost_usd = float(running_cost)
        wave.input_tokens = running_input_tokens
        wave.output_tokens = running_output_tokens
        await db.commit()

        # Parse decision — consensus across multiple review leads
        decision = _consensus_decision(review_results)
        review_timer.__exit__(None, None, None)

        # Emit review loop telemetry (Ticket 16.1)
        decisions_by_lead = {
            sr.agent_name: _parse_review_decision(sr.text)
            for sr in review_results
        }
        emit_review_loop_metrics(ReviewLoopMetrics(
            wave_id=execution_wave_id,
            iteration_number=iteration + 1,
            consensus_decision=decision,
            decisions_by_lead=decisions_by_lead,
            elapsed_seconds=review_timer.elapsed,
        ))

        logger.info(
            "Review decision (iteration %d): %s", iteration + 1, decision
        )

        if decision == "APPROVE":
            final_files = iteration_files
            break

        elif decision == "MINOR_FIX":
            # Lead(s) fix files directly
            for sr in review_results:
                fix_result = await _execute_minor_fix(
                    review_slot_data=next(
                        a for a in review_wave_data["agents"]
                        if a["output_key"] == sr.output_key
                    ),
                    review_text=sr.text,
                    current_files=iteration_files,
                    artifact_ctx=artifact_ctx,
                    project_ctx=project_ctx,
                )
                iteration_files.update(fix_result.files)
                running_cost += fix_result.cost
                running_input_tokens += fix_result.input_tokens
                running_output_tokens += fix_result.output_tokens
                await increment_costs(
                    db=db,
                    execution_wave_id=execution_wave_id,
                    artifact_id=artifact_ctx.id,
                    workspace_id=workspace_id,
                    cost=fix_result.cost,
                    input_tokens=fix_result.input_tokens,
                    output_tokens=fix_result.output_tokens,
                )

            wave.cost_usd = float(running_cost)
            wave.input_tokens = running_input_tokens
            wave.output_tokens = running_output_tokens
            await db.commit()
            final_files = iteration_files
            break

        else:  # REVISE
            # Merge feedback from all review leads
            merged_feedback: dict[str, str] = {}
            for sr in review_results:
                merged_feedback.update(_extract_review_feedback(sr.text))
            review_feedback = merged_feedback
            logger.info(
                "REVISE — feedback for slots: %s", list(review_feedback.keys())
            )
            # Continue to next iteration

    return (
        final_files,
        running_cost,
        running_input_tokens,
        running_output_tokens,
        all_assumptions,
        all_sources,
    )


# ---------------------------------------------------------------------------
# Delegation validation (Ticket 17.3, AD-27)
# ---------------------------------------------------------------------------

_MAX_VALIDATION_REPLANS: int = settings.AGENT_MAX_VALIDATION_REPLANS


def _parse_validation_decision(text: str) -> str:
    """Extract APPROVED | REVISE from a validation output.

    Falls back to APPROVED (fail-open) if the decision line is not found.
    """
    match = re.search(
        r"\*\*Decision:\*\*\s*(APPROVED|REVISE)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()

    upper = text.upper()
    if "REVISE" in upper:
        return "REVISE"
    return "APPROVED"


async def _run_delegation_validation(
    validation_wave_def: Any,
    planning_outputs: dict[str, WaveOutput],
    planning_files: dict[str, str],
    planning_waves: list[dict[str, Any]],
    execution_waves: list[dict[str, Any]],
    wave: Any,
    artifact_ctx: _ArtifactCtx,
    project_ctx: _ProjectCtx,
    workspace_id: str,
    execution_wave_id: str,
    delegation_plan: dict[str, str],
    running_cost: Decimal,
    running_input_tokens: int,
    running_output_tokens: int,
    all_assumptions: list[str],
    all_sources: list[str],
    waves_data: list[dict[str, Any]],
    db: AsyncSession,
) -> tuple[dict[str, str], dict[str, WaveOutput], dict[str, str], Decimal, int, int]:
    """Run the delegation validation step and handle REVISE with one re-plan.

    Returns updated: (delegation_plan, planning_outputs, planning_files,
                      running_cost, running_input_tokens, running_output_tokens)
    """
    # Build the validation wave_data from the DagWave definition
    validation_wave_data: dict[str, Any] = {
        "wave_number": 0,
        "label": validation_wave_def.label,
        "wave_type": "validation",
        "agents": [
            {
                "agent_id": None,  # Filled by _resolve_validation_agent below
                "role_in_wave": slot.role_prompt,
                "output_key": slot.slot_id,
                "depends_on": list(validation_wave_def.depends_on),
                "suggested_specializations": list(slot.suggested_specializations),
                "label": slot.label,
                "is_lead": slot.is_lead,
            }
            for slot in validation_wave_def.slots
        ],
    }

    # Resolve agent_id for validation slots from assembled_team
    assembled_team: list[dict[str, Any]] = wave.assembled_team or []
    for slot_data in validation_wave_data["agents"]:
        slot_data["agent_id"] = _find_best_agent_for_validation(
            slot_data["suggested_specializations"], assembled_team
        )

    for replan_attempt in range(_MAX_VALIDATION_REPLANS + 1):
        _check_budget(artifact_ctx, running_cost, 0)

        # Pre-populate validation context with planning text outputs
        planning_text_files: dict[str, str] = {}
        for key, output in planning_outputs.items():
            if output.text:
                planning_text_files[f"planning_{key}.md"] = output.text

        validation_results = await _run_wave_parallel(
            wave_data=validation_wave_data,
            wave_outputs=planning_outputs,
            artifact_ctx=artifact_ctx,
            project_ctx=project_ctx,
            phase="validation",
            shared_files=planning_text_files,
        )

        val_cost = Decimal("0")
        for sr in validation_results:
            val_cost += sr.cost
            running_input_tokens += sr.input_tokens
            running_output_tokens += sr.output_tokens
            all_assumptions.extend(sr.assumptions)

        running_cost += val_cost
        await increment_costs(
            db=db,
            execution_wave_id=execution_wave_id,
            artifact_id=artifact_ctx.id,
            workspace_id=workspace_id,
            cost=val_cost,
            input_tokens=sum(sr.input_tokens for sr in validation_results),
            output_tokens=sum(sr.output_tokens for sr in validation_results),
        )
        wave.cost_usd = float(running_cost)
        wave.input_tokens = running_input_tokens
        wave.output_tokens = running_output_tokens
        await db.commit()

        # Parse decision
        decisions = [_parse_validation_decision(sr.text) for sr in validation_results]
        decision = "REVISE" if "REVISE" in decisions else "APPROVED"

        logger.info(
            "Delegation validation (attempt %d): %s",
            replan_attempt + 1, decision,
        )

        await _broadcast_safe(
            "execution.wave_completed",
            {
                "artifact_id": artifact_ctx.id,
                "wave_number": 0,
                "total_waves": len(waves_data),
            },
        )

        if decision == "APPROVED":
            break

        if replan_attempt >= _MAX_VALIDATION_REPLANS:
            logger.warning(
                "Delegation validation still REVISE after %d re-plans — "
                "proceeding with current plan",
                _MAX_VALIDATION_REPLANS,
            )
            break

        # REVISE: re-run planning waves with validation feedback
        logger.info("Re-running planning waves with validation feedback")
        validation_feedback = "\n\n".join(sr.text for sr in validation_results)

        planning_outputs = {}
        planning_files = {}

        for wave_data in planning_waves:
            _check_budget(artifact_ctx, running_cost, wave_data["wave_number"])

            # Inject validation feedback into the planning slots' role prompts
            enriched_wave = _enrich_wave_with_feedback(wave_data, validation_feedback)

            slot_results = await _run_wave_parallel(
                wave_data=enriched_wave,
                wave_outputs=planning_outputs,
                artifact_ctx=artifact_ctx,
                project_ctx=project_ctx,
                phase="planning",
            )

            wave_cost = Decimal("0")
            for sr in slot_results:
                planning_outputs[sr.output_key] = WaveOutput(
                    text=sr.text,
                    agent_name=sr.agent_name,
                    slot_label=sr.slot_label,
                    files=list(sr.files.keys()),
                )
                planning_files.update(sr.files)
                wave_cost += sr.cost
                running_input_tokens += sr.input_tokens
                running_output_tokens += sr.output_tokens
                all_assumptions.extend(sr.assumptions)
                all_sources.extend(sr.sources)

            running_cost += wave_cost
            await increment_costs(
                db=db,
                execution_wave_id=execution_wave_id,
                artifact_id=artifact_ctx.id,
                workspace_id=workspace_id,
                cost=wave_cost,
                input_tokens=sum(sr.input_tokens for sr in slot_results),
                output_tokens=sum(sr.output_tokens for sr in slot_results),
            )
            wave.cost_usd = float(running_cost)
            wave.input_tokens = running_input_tokens
            wave.output_tokens = running_output_tokens
            await db.commit()

        # Re-extract delegation plan from updated planning outputs
        delegation_plan = _extract_delegation_plan(planning_outputs, execution_waves)
        logger.info(
            "Delegation plan re-extracted after validation: %d slots mapped",
            len(delegation_plan),
        )

    return (
        delegation_plan,
        planning_outputs,
        planning_files,
        running_cost,
        running_input_tokens,
        running_output_tokens,
    )


def _find_best_agent_for_validation(
    specializations: list[str],
    assembled_team: list[dict[str, Any]],
) -> str | None:
    """Find the best agent from assembled_team matching the validation slot specializations."""
    for agent_entry in assembled_team:
        agent_name = agent_entry.get("agent_name", "")
        for spec in specializations:
            if spec.lower() in agent_name.lower():
                return agent_entry.get("agent_id")
    # Fallback: return the first agent in the team
    if assembled_team:
        return assembled_team[0].get("agent_id")
    return None


def _enrich_wave_with_feedback(
    wave_data: dict[str, Any],
    validation_feedback: str,
) -> dict[str, Any]:
    """Create a copy of wave_data with validation feedback appended to each slot's role prompt."""
    enriched = dict(wave_data)
    enriched["agents"] = []
    for agent_data in wave_data["agents"]:
        enriched_agent = dict(agent_data)
        original_role = enriched_agent.get("role_in_wave", "")
        enriched_agent["role_in_wave"] = (
            f"{original_role}\n\n"
            f"## Delegation Validation Feedback\n"
            f"A validator reviewed your previous delegation plan and found issues. "
            f"Address all of the following feedback in your revised plan:\n\n"
            f"{validation_feedback}"
        )
        enriched["agents"].append(enriched_agent)
    return enriched


# ---------------------------------------------------------------------------
# Legacy flat-wave execution (backward compat for old templates)
# ---------------------------------------------------------------------------


async def _execute_legacy_dag(
    dag_plan: dict[str, Any],
    wave: ExecutionWave,
    artifact_ctx: _ArtifactCtx,
    project_ctx: _ProjectCtx,
    workspace_id: str,
    execution_wave_id: str,
    db: AsyncSession,
) -> tuple[dict[str, str], Decimal, int, int, list[str], list[str]]:
    """Run the original flat wave loop for templates without wave_type."""
    waves_data = dag_plan["waves"]
    total_steps = len(waves_data)

    wave_outputs: dict[str, WaveOutput] = {}
    running_cost = Decimal("0")
    running_input_tokens = 0
    running_output_tokens = 0
    all_assumptions: list[str] = []
    all_sources: list[str] = []
    all_files: dict[str, str] = {}

    for wave_data in waves_data:
        wave_number = wave_data["wave_number"]
        wave.current_step = wave_number
        await db.commit()

        _check_budget(artifact_ctx, running_cost, wave_number)

        slot_results = await _run_wave_parallel(
            wave_data=wave_data,
            wave_outputs=wave_outputs,
            artifact_ctx=artifact_ctx,
            project_ctx=project_ctx,
            phase="execution",
        )

        wave_cost = Decimal("0")
        for sr in slot_results:
            wave_outputs[sr.output_key] = WaveOutput(
                text=sr.text,
                agent_name=sr.agent_name,
                slot_label=sr.slot_label,
                files=list(sr.files.keys()),
            )
            wave_cost += sr.cost
            running_input_tokens += sr.input_tokens
            running_output_tokens += sr.output_tokens
            all_assumptions.extend(sr.assumptions)
            all_sources.extend(sr.sources)
            all_files.update(sr.files)

        running_cost += wave_cost
        await increment_costs(
            db=db,
            execution_wave_id=execution_wave_id,
            artifact_id=artifact_ctx.id,
            workspace_id=workspace_id,
            cost=wave_cost,
            input_tokens=sum(sr.input_tokens for sr in slot_results),
            output_tokens=sum(sr.output_tokens for sr in slot_results),
        )
        wave.cost_usd = float(running_cost)
        wave.input_tokens = running_input_tokens
        wave.output_tokens = running_output_tokens
        await db.commit()

        await _broadcast_safe(
            "execution.wave_completed",
            {
                "artifact_id": artifact_ctx.id,
                "wave_number": wave_number,
                "total_waves": total_steps,
            },
        )
        await _check_budget_warning(db, workspace_id)

    # Compile if needed
    needs_compile: bool = dag_plan.get("needs_compile", False)
    if needs_compile:
        compile_result = await _execute_compile(wave_outputs, artifact_ctx, project_ctx)
        all_files.update(compile_result.files)
        if compile_result.text and not compile_result.files:
            all_files["output.md"] = compile_result.text
        running_cost += compile_result.cost
        running_input_tokens += compile_result.input_tokens
        running_output_tokens += compile_result.output_tokens
        all_assumptions.extend(compile_result.assumptions)
        all_sources.extend(compile_result.sources)
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

    if not all_files:
        all_files = _text_outputs_to_files(wave_outputs, waves_data, artifact_ctx.artifact_type)

    return (
        all_files,
        running_cost,
        running_input_tokens,
        running_output_tokens,
        all_assumptions,
        all_sources,
    )


# ---------------------------------------------------------------------------
# Wave execution — parallel slots
# ---------------------------------------------------------------------------

_SLOT_MAX_RETRIES: int = settings.AGENT_SLOT_MAX_RETRIES
_SLOT_RETRY_BACKOFF_BASE: int = settings.AGENT_SLOT_RETRY_BACKOFF_BASE


async def _run_wave_parallel(
    wave_data: dict[str, Any],
    wave_outputs: dict[str, WaveOutput],
    artifact_ctx: _ArtifactCtx,
    project_ctx: _ProjectCtx,
    phase: Phase = "execution",
    delegation_plan: dict[str, str] | None = None,
    review_feedback: dict[str, str] | None = None,
    shared_files: dict[str, str] | None = None,
    review_criteria: tuple[str, ...] = (),
) -> list[SlotResult]:
    """Execute all slots in a wave concurrently. Raises SlotExecutionError on any failure."""
    agents_in_wave: list[dict[str, Any]] = wave_data["agents"]

    slot_coros = [
        _execute_slot(
            slot_data=slot_data,
            wave_outputs=wave_outputs,
            artifact_ctx=artifact_ctx,
            project_ctx=project_ctx,
            phase=phase,
            delegation_plan=delegation_plan or {},
            review_feedback=review_feedback or {},
            shared_files=shared_files or {},
            review_criteria=review_criteria,
        )
        for slot_data in agents_in_wave
    ]

    results = await asyncio.gather(*slot_coros, return_exceptions=True)

    slot_results: list[SlotResult] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            failed_key = agents_in_wave[i].get("output_key", f"slot_{i}")
            logger.error("Slot '%s' failed: %s", failed_key, result, exc_info=result)
            raise SlotExecutionError(slot_key=failed_key, message=str(result)) from result
        slot_results.append(result)

    return slot_results


async def _execute_slot(
    slot_data: dict[str, Any],
    wave_outputs: dict[str, WaveOutput],
    artifact_ctx: _ArtifactCtx,
    project_ctx: _ProjectCtx,
    phase: Phase = "execution",
    delegation_plan: dict[str, str] | None = None,
    review_feedback: dict[str, str] | None = None,
    shared_files: dict[str, str] | None = None,
    review_criteria: tuple[str, ...] = (),
) -> SlotResult:
    """Execute a single DAG slot."""
    agent_id: str | None = slot_data.get("agent_id")
    output_key: str = slot_data["output_key"]
    depends_on: list[str] = slot_data.get("depends_on", [])

    if agent_id is None:
        raise SlotExecutionError(slot_key=output_key, message="No agent_id assigned to slot")

    async with async_session_maker() as db:
        agent = await db.get(Agent, agent_id)
        if agent is None:
            raise SlotExecutionError(slot_key=output_key, message=f"Agent '{agent_id}' not found")

        agent_name: str = agent.name
        model_tier: str = agent.model_tier
        agent.status = "working"
        await db.flush()

        try:
            agent_memory: str = await load_agent_memory(agent_id, db)

            slot_deps = SimpleNamespace(depends_on=depends_on)
            upstream_context: str | None = build_upstream_context(slot_deps, wave_outputs)

            output_format_rules: str = get_output_format_rules(
                artifact_ctx.artifact_type, output_key
            )
            system_prompt: str = build_system_prompt(agent, output_format_rules)

            # Build effective role: base + delegated task + review feedback
            effective_role = _build_slot_effective_role(
                slot_data=slot_data,
                delegation_plan=delegation_plan or {},
                review_feedback=review_feedback or {},
            )

            # Append grading criteria for review slots (Ticket 17.2)
            if phase == "review" and review_criteria:
                criteria_block = build_review_criteria_block(review_criteria)
                if criteria_block:
                    effective_role = effective_role + "\n\n" + criteria_block

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
                wave_task=effective_role,
            )

            tools = get_tools_for_phase(phase)

            # Pre-populate files so review/minor-fix leads can read worker outputs
            initial_files = dict(shared_files) if shared_files else {}
            exec_context = ExecutionContext(
                files=initial_files,
                project_id=project_ctx.id,
                workspace_id=artifact_ctx.workspace_id,
                db_session=db,
            )
            tool_executor = create_tool_executor(tools, exec_context)
            model_id: str = _resolve_model_id(model_tier)

            last_exc: Exception | None = None
            timer = Timer()
            for attempt in range(_SLOT_MAX_RETRIES):
                try:
                    with timer:
                        result: AgentResult = await run_agent(
                            system_prompt=system_prompt,
                            user_message=user_message,
                            tools=tools,
                            model=model_id,
                            tool_executor=tool_executor,
                        )
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt < _SLOT_MAX_RETRIES - 1:
                        wait = _SLOT_RETRY_BACKOFF_BASE ** (attempt + 1)
                        logger.warning(
                            "Slot '%s' attempt %d/%d failed — retrying in %ds: %s",
                            output_key, attempt + 1, _SLOT_MAX_RETRIES, wait, exc,
                        )
                        await asyncio.sleep(wait)
                    else:
                        raise SlotExecutionError(slot_key=output_key, message=str(exc)) from exc

            cost: Decimal = compute_call_cost(result.input_tokens, result.output_tokens, model_tier)

            # Emit telemetry (Ticket 16.1)
            emit_execution_metrics(ExecutionMetrics(
                wave_id=artifact_ctx.id,
                slot_key=output_key,
                agent_id=agent_id,
                phase=phase,
                model=model_id,
                tool_loop_iterations=result.tool_loop_iterations,
                tool_calls=result.tool_calls_log,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                elapsed_seconds=timer.elapsed,
                context_tokens_peak=result.context_tokens_peak,
            ))

            # Merge agent-produced files (covers real file_write calls AND mocked AgentResults)
            exec_context.files.update(result.files)

            return SlotResult(
                output_key=output_key,
                agent_name=agent_name,
                slot_label=slot_data.get("label", output_key),
                text=result.text,
                files=exec_context.files,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost=cost,
                assumptions=result.assumptions,
                sources=result.sources,
            )

        finally:
            agent.status = "ready"
            try:
                await db.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Minor-fix execution
# ---------------------------------------------------------------------------


async def _execute_minor_fix(
    review_slot_data: dict[str, Any],
    review_text: str,
    current_files: dict[str, str],
    artifact_ctx: _ArtifactCtx,
    project_ctx: _ProjectCtx,
) -> SlotResult:
    """Run the review lead with file_write access to apply minor corrections."""
    agent_id: str | None = review_slot_data.get("agent_id")
    output_key: str = review_slot_data["output_key"]

    if agent_id is None:
        logger.warning("Minor fix: no agent_id for slot %s, skipping", output_key)
        return SlotResult(
            output_key=output_key + "_fix",
            agent_name="Unknown",
            slot_label="Minor Fix (skipped)",
            text="",
            files={},
            input_tokens=0,
            output_tokens=0,
            cost=Decimal("0"),
            assumptions=[],
            sources=[],
        )

    async with async_session_maker() as db:
        agent = await db.get(Agent, agent_id)
        if agent is None:
            logger.warning("Minor fix: agent '%s' not found, skipping", agent_id)
            return SlotResult(
                output_key=output_key + "_fix",
                agent_name="Unknown",
                slot_label="Minor Fix (skipped)",
                text="",
                files={},
                input_tokens=0,
                output_tokens=0,
                cost=Decimal("0"),
                assumptions=[],
                sources=[],
            )

        model_tier = agent.model_tier
        agent.status = "working"
        await db.flush()

        try:
            files_summary = "\n".join(
                f"  - {path} ({len(content)} chars)"
                for path, content in sorted(current_files.items())
            )

            user_message = (
                f"You reviewed the work and decided MINOR_FIX. "
                f"Apply your corrections directly using file_read and file_write.\n\n"
                f"## Your Review\n{review_text}\n\n"
                f"## Available Files\n{files_summary}\n\n"
                f"Use file_read to examine files you need to correct, then file_write "
                f"to apply your changes. Fix exactly what you identified — do not rewrite "
                f"unrelated code."
            )

            # Minor fix uses execution phase (file_read + file_write)
            tools = get_tools_for_phase("execution")
            exec_context = ExecutionContext(
                files=dict(current_files),
                project_id=project_ctx.id,
                workspace_id=artifact_ctx.workspace_id,
                db_session=db,
            )
            tool_executor = create_tool_executor(tools, exec_context)
            model_id = _resolve_model_id(model_tier)

            timer = Timer()
            with timer:
                result: AgentResult = await run_agent(
                    system_prompt=_MINOR_FIX_SYSTEM_PROMPT,
                    user_message=user_message,
                    tools=tools,
                    model=model_id,
                    tool_executor=tool_executor,
                )

            cost = compute_call_cost(result.input_tokens, result.output_tokens, model_tier)

            # Emit telemetry (Ticket 16.1)
            emit_execution_metrics(ExecutionMetrics(
                wave_id=artifact_ctx.id,
                slot_key=output_key + "_fix",
                agent_id=agent_id,
                phase="execution",
                model=model_id,
                tool_loop_iterations=result.tool_loop_iterations,
                tool_calls=result.tool_calls_log,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                elapsed_seconds=timer.elapsed,
                context_tokens_peak=result.context_tokens_peak,
            ))

            return SlotResult(
                output_key=output_key + "_fix",
                agent_name=agent.name,
                slot_label="Minor Fix",
                text=result.text,
                files=exec_context.files,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost=cost,
                assumptions=result.assumptions,
                sources=result.sources,
            )
        finally:
            agent.status = "ready"
            try:
                await db.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Delegation plan extraction
# ---------------------------------------------------------------------------


def _extract_delegation_plan(
    planning_outputs: dict[str, WaveOutput],
    execution_waves_data: list[dict[str, Any]],
) -> dict[str, str]:
    """Map execution slot_ids to their delegated task text from planning outputs.

    Scans every planning output for '## Specialist Delegation' sections and
    matches each '### Role Name' sub-section against execution slot specializations.
    """
    delegation_plan: dict[str, str] = {}

    for wave_data in execution_waves_data:
        for slot_data in wave_data["agents"]:
            slot_id: str = slot_data["output_key"]
            specializations: list[str] = slot_data.get("suggested_specializations", [])
            label: str = slot_data.get("label", "")

            for output in planning_outputs.values():
                section = _find_delegation_section(output.text, specializations, label)
                if section:
                    delegation_plan[slot_id] = section
                    break

    return delegation_plan


def _find_delegation_section(
    planning_text: str,
    specializations: list[str],
    label: str,
) -> str | None:
    """Find the delegation section for a specialist role within a planning output."""
    marker = "## Specialist Delegation"
    idx = planning_text.find(marker)
    if idx == -1:
        return None

    delegation_text = planning_text[idx + len(marker):]
    raw_sections = re.split(r"\n###\s+", delegation_text)

    for raw in raw_sections[1:]:  # first element is empty prefix
        lines = raw.strip().split("\n", 1)
        if not lines:
            continue
        header = lines[0].strip().lower()
        content = lines[1].strip() if len(lines) > 1 else ""
        if not content:
            continue

        # Match header against specializations (partial, case-insensitive)
        for spec in specializations:
            spec_lower = spec.lower()
            if spec_lower in header or header in spec_lower:
                return content

        # Also match against slot label words
        if label:
            label_words = set(label.lower().split())
            header_words = set(header.split())
            if label_words & header_words:  # any word overlap
                return content

    return None


def _build_slot_effective_role(
    slot_data: dict[str, Any],
    delegation_plan: dict[str, str],
    review_feedback: dict[str, str],
) -> str:
    """Build the effective role prompt: base + delegated task + review feedback."""
    slot_id: str = slot_data["output_key"]
    specializations: list[str] = slot_data.get("suggested_specializations", [])
    base_role: str = slot_data["role_in_wave"]

    parts: list[str] = []

    # Inject delegated task
    delegated = delegation_plan.get(slot_id)
    if delegated:
        parts.append(f"## Your Delegated Task\n{delegated}")

    # Inject review feedback (match by specialization)
    feedback = _match_feedback_to_slot(specializations, slot_id, review_feedback)
    if feedback:
        parts.append(
            f"## Review Feedback (Iteration)\n"
            f"The reviewing lead found issues in your previous output and requires changes:\n\n"
            f"{feedback}\n\n"
            f"Address every point above in this iteration."
        )

    if parts:
        return base_role + "\n\n" + "\n\n".join(parts)
    return base_role


def _match_feedback_to_slot(
    specializations: list[str],
    slot_id: str,
    review_feedback: dict[str, str],
) -> str | None:
    """Find review feedback for a slot by matching specializations to feedback keys."""
    if not review_feedback:
        return None

    # Exact slot_id match
    if slot_id in review_feedback:
        return review_feedback[slot_id]

    # Wildcard / broadcast feedback
    if "_all" in review_feedback:
        return review_feedback["_all"]

    # Partial match on specialization names
    for spec in specializations:
        spec_lower = spec.lower()
        for fb_key, fb_text in review_feedback.items():
            if spec_lower in fb_key.lower() or fb_key.lower() in spec_lower:
                return fb_text

    return None


# ---------------------------------------------------------------------------
# Review decision parsing
# ---------------------------------------------------------------------------


def _parse_review_decision(text: str) -> str:
    """Extract APPROVE | MINOR_FIX | REVISE from a review output.

    Falls back to REVISE if the structured decision line is not found.
    """
    match = re.search(
        r"\*\*Decision:\*\*\s*(APPROVE|MINOR_FIX|REVISE)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()

    # Fallback: scan for bare keywords
    upper = text.upper()
    for keyword in ("APPROVE", "MINOR_FIX", "REVISE"):
        if keyword in upper:
            return keyword

    logger.warning("Could not parse review decision — defaulting to REVISE")
    return "REVISE"


def _consensus_decision(review_results: list[SlotResult]) -> str:
    """Determine consensus when multiple leads review in parallel.

    Priority: REVISE > MINOR_FIX > APPROVE
    (any dissent blocks approval; REVISE is the most conservative option)
    """
    if not review_results:
        return "APPROVE"

    decisions = [_parse_review_decision(sr.text) for sr in review_results]

    if "REVISE" in decisions:
        return "REVISE"
    if "MINOR_FIX" in decisions:
        return "MINOR_FIX"
    return "APPROVE"


def _extract_review_feedback(review_text: str) -> dict[str, str]:
    """Extract per-specialist feedback from a REVISE decision.

    Returns a dict keyed by role name (e.g., 'Backend Developer').
    If no structured feedback section exists, returns {'_all': full_text}.
    """
    marker = "## Specialist Feedback"
    idx = review_text.find(marker)
    if idx == -1:
        return {"_all": review_text}

    feedback_text = review_text[idx + len(marker):]
    raw_sections = re.split(r"\n###\s+", feedback_text)

    feedback: dict[str, str] = {}
    for raw in raw_sections[1:]:
        lines = raw.strip().split("\n", 1)
        if not lines:
            continue
        role_name = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ""
        if role_name and content:
            feedback[role_name] = content

    if not feedback:
        feedback["_all"] = review_text

    return feedback


# ---------------------------------------------------------------------------
# Compilation (legacy templates)
# ---------------------------------------------------------------------------


async def _execute_compile(
    wave_outputs: dict[str, WaveOutput],
    artifact_ctx: _ArtifactCtx,
    project_ctx: _ProjectCtx,
) -> SlotResult:
    all_keys = list(wave_outputs.keys())
    compile_deps = SimpleNamespace(depends_on=all_keys)
    upstream_context = build_upstream_context(compile_deps, wave_outputs)

    artifact_brief = {
        "title": artifact_ctx.title,
        "goal": artifact_ctx.goal,
        "target_audience": artifact_ctx.target_audience,
        "context": artifact_ctx.context,
        "description": artifact_ctx.description,
    }
    output_format_rules = get_output_format_rules(artifact_ctx.artifact_type, "compiler")
    system_prompt = (
        f"{_COMPILE_SYSTEM_PROMPT}\n\n{AUTO_ASSUME_RULE}\n\n{output_format_rules}"
    )
    user_message = build_user_message(
        agent_memory=None,
        upstream_context=upstream_context,
        project_brief=project_ctx.brief_published,
        artifact_brief=artifact_brief,
        wave_task=_COMPILE_TASK,
    )

    tools = get_tools_for_phase("execution")
    exec_context = ExecutionContext(
        project_id=project_ctx.id,
        workspace_id=artifact_ctx.workspace_id,
    )
    tool_executor = create_tool_executor(tools, exec_context)
    model_id = _resolve_model_id("sonnet")

    result: AgentResult = await run_agent(
        system_prompt=system_prompt,
        user_message=user_message,
        tools=tools,
        model=model_id,
        tool_executor=tool_executor,
    )
    cost = compute_call_cost(result.input_tokens, result.output_tokens, "sonnet")

    # Merge agent-produced files (covers real file_write calls AND mocked AgentResults)
    exec_context.files.update(result.files)

    return SlotResult(
        output_key="_compile",
        agent_name="Compiler",
        slot_label="Compilation",
        text=result.text,
        files=exec_context.files,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost=cost,
        assumptions=result.assumptions,
        sources=result.sources,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_budget(
    artifact_ctx: _ArtifactCtx,
    running_cost: Decimal,
    wave_number: int,
) -> None:
    projected = artifact_ctx.total_cost_usd + running_cost
    if projected > artifact_ctx.max_budget_usd:
        raise BudgetExceededError(
            f"Budget exceeded before wave {wave_number}: "
            f"${projected} > ${artifact_ctx.max_budget_usd}"
        )


def _text_outputs_to_files(
    wave_outputs: dict[str, WaveOutput],
    waves_data: list[dict[str, Any]],
    artifact_type: str,
) -> dict[str, str]:
    """Fallback: convert last-wave text outputs to files when no file_write was used."""
    files: dict[str, str] = {}
    if not waves_data:
        return files
    last_wave_agents = waves_data[-1].get("agents", [])
    for agent_data in last_wave_agents:
        key = agent_data["output_key"]
        wo = wave_outputs.get(key)
        if wo and wo.text:
            ext = "md" if artifact_type == "prose" else "txt"
            files[f"{key}.{ext}"] = wo.text
    return files


def _guess_content_type(file_path: str) -> str:
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
    try:
        from app.core.git_push import push_artifact_to_git, push_iteration_to_git

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
        logger.exception("Git push failed (non-fatal) for artifact %s", artifact_id)


async def _broadcast_safe(event_type: str, payload: dict[str, Any]) -> None:
    try:
        from app.api.websocket_manager import broadcast_event
        await broadcast_event(event_type, payload)
    except Exception:
        logger.debug("WebSocket broadcast failed (non-fatal): %s", event_type)


async def _check_budget_warning(db: AsyncSession, workspace_id: str) -> None:
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
