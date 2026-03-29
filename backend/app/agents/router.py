"""Auto-assembly & DAG router — selects a template and maps agents to slots.

Ref: TDD-03 Section 3 (auto-assembly & routing),
     TDD-03 Section 3.1 (design — single combined Haiku call, AD-9),
     TDD-03 Section 3.2 (system prompt),
     TDD-03 Section 3.3 (user message format),
     TDD-03 Section 3.4 (JSON response schema),
     TDD-03 Section 3.5 (post-processing),
     TDD-03 Section 3.6 (cost estimation),
     TDD-03 Section 10.2 (readiness gate — 50 threshold).

Flow: format brief + roster for Haiku → call Haiku → parse JSON →
validate → hydrate DAG plan → estimate cost → return ``RoutingResult``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from app.agents.anthropic_runner import get_anthropic_client
from app.agents.dag_templates import TEMPLATE_REGISTRY, get_template
from app.agents.dag_templates.schema import DagTemplate
from app.config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Readiness gate (TDD-03 Section 10.2)
# ---------------------------------------------------------------------------

READINESS_GATE: int = 50
"""Agents below this score are excluded from the roster presented to Haiku."""

# ---------------------------------------------------------------------------
# Cost estimation (TDD-03 Section 3.6)
# ---------------------------------------------------------------------------

_PER_SLOT_COST: dict[str, Decimal] = {
    "sonnet": Decimal("0.042"),   # (4000 * 0.003 + 2000 * 0.015) / 1000
    "opus": Decimal("0.210"),     # (4000 * 0.015 + 2000 * 0.075) / 1000
}

_DEFAULT_SLOT_COST: Decimal = Decimal("0.042")  # default to sonnet pricing

# ---------------------------------------------------------------------------
# Protocols — what the router needs from artifact and agent objects
# ---------------------------------------------------------------------------


@runtime_checkable
class ArtifactBrief(Protocol):
    """Minimal interface for the artifact fields the router reads."""

    @property
    def title(self) -> str: ...

    @property
    def artifact_type(self) -> str: ...

    @property
    def goal(self) -> str | None: ...

    @property
    def target_audience(self) -> str | None: ...

    @property
    def context(self) -> str | None: ...

    @property
    def description(self) -> str | None: ...


@runtime_checkable
class RosterAgent(Protocol):
    """Minimal interface for the agent fields the router reads."""

    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def specialization(self) -> str: ...

    @property
    def readiness_score(self) -> int: ...

    @property
    def progression_level(self) -> str: ...

    @property
    def model_tier(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def role(self) -> str: ...

    @property
    def archived_at(self) -> Any: ...


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """Immutable result from ``route_brief()``."""

    template_key: str
    """The selected DAG template ID (e.g., ``"code_feature"``)."""

    dag_plan: dict[str, Any]
    """JSONB-ready dict matching TDD-02 Section 3.3 schema."""

    assembled_team: list[dict[str, str]]
    """Deduplicated list of agent dicts ``{"agent_id": ..., "agent_name": ...}``."""

    step_labels: list[str]
    """Human-readable wave labels for heartbeat UI."""

    estimated_cost: Decimal
    """Rough cost estimate in USD."""

    reasoning: str
    """Haiku's reasoning for the template/agent selections."""

    warnings: list[str] = field(default_factory=list)
    """Non-fatal issues (e.g., low-readiness agents assigned to slots)."""

    is_fallback: bool = False
    """True if the result was produced by the fallback path (not Haiku)."""


# ---------------------------------------------------------------------------
# System prompt (TDD-03 Section 3.2 — verbatim)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = """\
You are a Project Router. Given a user's brief and their available AI agent roster,
your job is to:

1. Select the best execution template for this brief.
2. Assign the best-matching agent from the roster to each slot in the template.

Rules:
- Match agents to slots based on their specialization. Pick the agent whose
  specialization is closest to the slot's suggested_specializations.
- CRITICAL — lead/worker matching:
  Slots marked is_lead=true are for strategic leads (planning, delegation, review).
  Assign ONLY agents with role=lead to is_lead=true slots.
  Assign agents with role=worker to is_lead=false (execution) slots.
  If no worker matches an execution slot, use the best available agent.
- Every slot MUST be filled. If no agent closely matches a slot, assign the
  most general-purpose agent with the correct role.
- Never assign the same agent to two slots in the same wave (parallel conflict).
  An agent CAN appear in different waves (sequential is safe).
- If a slot has no good match at all, set agent_id to null — the system will
  use a generic agent with the slot's role_prompt as its specialization.

Respond with valid JSON only. No markdown, no explanation."""

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_brief_for_router(artifact: ArtifactBrief) -> str:
    """Format artifact brief fields into the user message section (TDD-03 Section 3.3)."""
    lines: list[str] = [
        "## Brief",
        "",
        f"Title: {artifact.title}",
        f"Type: {artifact.artifact_type}",
    ]
    if artifact.goal:
        lines.append(f"Goal: {artifact.goal}")
    if artifact.target_audience:
        lines.append(f"Target Audience: {artifact.target_audience}")
    if artifact.context:
        lines.append(f"Context: {artifact.context}")
    if artifact.description:
        lines.append(f"Description: {artifact.description}")
    return "\n".join(lines)


def _format_templates_for_router() -> str:
    """Format all registered templates for the user message (TDD-03 Section 3.3)."""
    sections: list[str] = ["## Available Templates", ""]
    for template in TEMPLATE_REGISTRY.values():
        slots_summary: list[str] = [
            f'{slot.slot_id} ({slot.label})'
            for wave in template.waves
            for slot in wave.slots
        ]
        sections.append(f"### {template.template_id}: {template.name}")
        sections.append(template.description)
        sections.append(f"Type: {template.artifact_type}")
        sections.append(f"Slots: {slots_summary}")
        sections.append("")
    return "\n".join(sections)


def format_roster_for_router(agents: list[RosterAgent]) -> str:
    """Format agent roster into the user message section (TDD-03 Section 3.3).

    Only includes agents that pass the readiness gate and are active
    (not archived, status is ``ready`` or ``working``).
    """
    eligible = _filter_eligible_agents(agents)
    if not eligible:
        return "## Your Roster (agents available for assignment)\n\n(No eligible agents)"

    lines: list[str] = ["## Your Roster (agents available for assignment)", ""]
    for agent in eligible:
        lines.append(
            f"- id: {agent.id} | name: {agent.name} "
            f"| role: {agent.role} "
            f"| specialization: {agent.specialization} "
            f"| readiness: {agent.readiness_score} "
            f"| progression: {agent.progression_level}"
        )
    return "\n".join(lines)


def _filter_eligible_agents(agents: list[RosterAgent]) -> list[RosterAgent]:
    """Return agents that pass the readiness gate and are not archived.

    Readiness gate: ``readiness_score >= 50`` (TDD-03 Section 10.2).
    """
    return [
        a for a in agents
        if a.readiness_score >= READINESS_GATE
        and a.archived_at is None
    ]


# ---------------------------------------------------------------------------
# Cost estimation (TDD-03 Section 3.6)
# ---------------------------------------------------------------------------


def estimate_cost(template: DagTemplate, model_tier: str = "sonnet") -> Decimal:
    """Rough cost estimate: ~4K input + ~2K output per agent slot.

    Formula from TDD-03 Section 3.6::

        total_slots = sum(len(wave.slots) for wave in template.waves)
        cost = total_slots * per_slot_cost[model_tier]
    """
    total_slots: int = sum(len(wave.slots) for wave in template.waves)
    per_slot: Decimal = _PER_SLOT_COST.get(model_tier, _DEFAULT_SLOT_COST)
    return (per_slot * total_slots).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Post-processing (TDD-03 Section 3.5)
# ---------------------------------------------------------------------------


def _build_dag_plan(
    template: DagTemplate,
    slot_assignments: dict[str, dict[str, str | None]],
) -> dict[str, Any]:
    """Hydrate the template into the ``dag_plan`` JSONB schema.

    Produces::

        {
          "template_id": "...",
          "needs_compile": false,
          "max_iterations": 3,
          "waves": [
            {
              "wave_number": 1,
              "label": "...",
              "wave_type": "planning",
              "agents": [
                {
                  "agent_id": "uuid-...",
                  "role_in_wave": "...",
                  "output_key": "slot_id",
                  "is_lead": true,
                  "suggested_specializations": ["Tech Lead", "..."],
                  "depends_on": ["other_slot_id"]
                }
              ]
            }
          ]
        }
    """
    waves: list[dict[str, Any]] = []
    for wave in template.waves:
        agents_in_wave: list[dict[str, Any]] = []
        for slot in wave.slots:
            assignment = slot_assignments.get(slot.slot_id, {})
            agent_entry: dict[str, Any] = {
                "agent_id": assignment.get("agent_id"),
                "role_in_wave": slot.role_prompt,
                "output_key": slot.slot_id,
                "label": slot.label,
                "is_lead": slot.is_lead,
                "suggested_specializations": list(slot.suggested_specializations),
            }
            if wave.depends_on:
                agent_entry["depends_on"] = list(wave.depends_on)
            agents_in_wave.append(agent_entry)

        waves.append({
            "wave_number": wave.wave_number,
            "label": wave.label,
            "wave_type": wave.wave_type,
            "agents": agents_in_wave,
        })
    return {
        "template_id": template.template_id,
        "needs_compile": template.needs_compile,
        "max_iterations": template.max_iterations,
        "waves": waves,
    }


def _build_assembled_team(
    slot_assignments: dict[str, dict[str, str | None]],
) -> list[dict[str, str]]:
    """Deduplicated list of assigned agents (TDD-03 Section 3.5, step 3)."""
    seen: set[str] = set()
    team: list[dict[str, str]] = []
    for assignment in slot_assignments.values():
        agent_id = assignment.get("agent_id")
        agent_name = assignment.get("agent_name", "")
        if agent_id and agent_id not in seen:
            seen.add(agent_id)
            team.append({"agent_id": agent_id, "agent_name": str(agent_name)})
    return team


def _build_step_labels(template: DagTemplate) -> list[str]:
    """Wave labels for heartbeat UI (TDD-03 Section 3.5, step 4)."""
    return [wave.label for wave in template.waves]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_haiku_response(
    parsed: dict[str, Any],
    agent_id_set: set[str],
) -> list[str]:
    """Validate the parsed Haiku JSON response.

    Returns a list of error strings.  Empty list = valid.

    Checks:
    1. ``template_id`` exists in the registry.
    2. ``slot_assignments`` is a dict.
    3. All assigned ``agent_id`` values exist in the provided roster set
       (``None``/null is allowed — system provides a generic agent).
    4. No two slots in the same wave have the same agent_id (parallel conflict).
    """
    errors: list[str] = []

    template_id = parsed.get("template_id")
    if not template_id or template_id not in TEMPLATE_REGISTRY:
        errors.append(f"Unknown template_id: {template_id!r}")
        return errors  # can't validate slots without a valid template

    slot_assignments = parsed.get("slot_assignments")
    if not isinstance(slot_assignments, dict):
        errors.append("slot_assignments is not a dict")
        return errors

    template = TEMPLATE_REGISTRY[template_id]

    # Check all template slots are assigned.
    all_slot_ids: set[str] = {
        slot.slot_id for wave in template.waves for slot in wave.slots
    }
    missing_slots = all_slot_ids - set(slot_assignments.keys())
    if missing_slots:
        errors.append(f"Missing slot assignments: {missing_slots}")

    # Check agent_id values exist in roster.
    for slot_id, assignment in slot_assignments.items():
        if not isinstance(assignment, dict):
            errors.append(f"Slot {slot_id!r}: assignment is not a dict")
            continue
        agent_id = assignment.get("agent_id")
        if agent_id is not None and agent_id not in agent_id_set:
            errors.append(
                f"Slot {slot_id!r}: agent_id {agent_id!r} not in roster"
            )

    # Check parallel conflicts (same agent in same wave).
    for wave in template.waves:
        wave_agent_ids: list[str] = []
        for slot in wave.slots:
            assignment = slot_assignments.get(slot.slot_id, {})
            if isinstance(assignment, dict):
                aid = assignment.get("agent_id")
                if aid is not None:
                    wave_agent_ids.append(aid)
        if len(wave_agent_ids) != len(set(wave_agent_ids)):
            errors.append(
                f"Wave {wave.wave_number}: parallel conflict "
                f"(same agent assigned to multiple slots)"
            )

    return errors


# ---------------------------------------------------------------------------
# Lead-slot enforcement (post-processing)
# ---------------------------------------------------------------------------


def _enforce_lead_assignments(
    slot_assignments: dict[str, dict[str, str | None]],
    template: "DagTemplate",
    eligible: list[RosterAgent],
) -> tuple[dict[str, dict[str, str | None]], list[str]]:
    """Ensure lead slots get lead agents and execution slots get worker agents.

    Haiku is instructed to respect roles, but may occasionally mismatch. This
    function corrects any mismatches by substituting the best-matching agent
    with the correct role.

    Returns (corrected_assignments, substitution_warnings).
    """
    agent_lookup: dict[str, RosterAgent] = {a.id: a for a in eligible}
    leads = [a for a in eligible if a.role == "lead"]
    workers = [a for a in eligible if a.role == "worker"]

    corrected = dict(slot_assignments)
    warnings: list[str] = []

    for wave in template.waves:
        for slot in wave.slots:
            assignment = corrected.get(slot.slot_id, {})
            if not isinstance(assignment, dict):
                continue

            agent_id = assignment.get("agent_id")
            if agent_id is None:
                continue

            agent = agent_lookup.get(agent_id)
            if agent is None:
                continue

            if slot.is_lead and agent.role != "lead":
                # Substitute with best lead (prefer highest readiness)
                if leads:
                    # Avoid parallel conflict: exclude leads already in this wave
                    wave_ids_used = {
                        corrected.get(s.slot_id, {}).get("agent_id")
                        for s in wave.slots
                        if s.slot_id != slot.slot_id
                    }
                    candidates = [a for a in leads if a.id not in wave_ids_used]
                    if not candidates:
                        candidates = leads  # parallel conflict unavoidable
                    best_lead = max(candidates, key=lambda a: a.readiness_score)
                    warnings.append(
                        f"Slot '{slot.slot_id}': substituted worker agent '{agent.name}' "
                        f"with lead agent '{best_lead.name}' (is_lead slot requires lead role)"
                    )
                    corrected[slot.slot_id] = {
                        "agent_id": best_lead.id,
                        "agent_name": best_lead.name,
                    }

    return corrected, warnings


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def _build_fallback_result(
    agents: list[RosterAgent],
    reason: str,
) -> RoutingResult:
    """Produce a ``bug_fix`` fallback when Haiku fails or returns garbage.

    Uses the simplest lead-structured template. Picks the best lead agent for
    planning/review slots and the best worker for the execution slot. Falls
    back to any available agent if no role-specific agents exist.
    """
    template = get_template("bug_fix")
    eligible = _filter_eligible_agents(agents)

    # If no eligible agents, try non-archived
    if not eligible:
        eligible = [a for a in agents if a.archived_at is None]

    leads = [a for a in eligible if a.role == "lead"]
    workers = [a for a in eligible if a.role == "worker"]

    best_lead = max(leads, key=lambda a: a.readiness_score) if leads else (
        max(eligible, key=lambda a: a.readiness_score) if eligible else None
    )
    best_worker = max(workers, key=lambda a: a.readiness_score) if workers else best_lead

    slot_assignments: dict[str, dict[str, str | None]] = {}
    for wave in template.waves:
        for slot in wave.slots:
            if slot.is_lead:
                agent = best_lead
            else:
                agent = best_worker
            slot_assignments[slot.slot_id] = {
                "agent_id": agent.id if agent else None,
                "agent_name": agent.name if agent else "Generic Agent",
            }

    model_tier = best_lead.model_tier if best_lead else "sonnet"

    return RoutingResult(
        template_key=template.template_id,
        dag_plan=_build_dag_plan(template, slot_assignments),
        assembled_team=_build_assembled_team(slot_assignments),
        step_labels=_build_step_labels(template),
        estimated_cost=estimate_cost(template, model_tier),
        reasoning=f"Fallback to bug_fix: {reason}",
        warnings=[f"Using fallback: {reason}"],
        is_fallback=True,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def route_brief(
    artifact: ArtifactBrief,
    roster_agents: list[RosterAgent],
) -> RoutingResult:
    """Select a DAG template and map agents to slots via a single Haiku call.

    This is the main entry point for the routing layer (TDD-03 Section 3.1,
    AD-9).  A single Haiku call both selects the template and assigns agents.

    Args:
        artifact: The artifact whose brief fields drive template selection.
        roster_agents: All agents in the workspace roster (pre-readiness-filter).

    Returns:
        ``RoutingResult`` with the hydrated DAG plan, assembled team, cost
        estimate, and Haiku's reasoning.  On any failure, returns a
        ``bug_fix`` fallback.
    """
    eligible = _filter_eligible_agents(roster_agents)
    if not eligible:
        return _build_fallback_result(
            roster_agents,
            "No agents meet the readiness gate",
        )

    # Build agent ID lookup for validation.
    agent_id_set: set[str] = {a.id for a in eligible}

    # Build the user message (TDD-03 Section 3.3).
    user_message: str = "\n\n".join([
        format_brief_for_router(artifact),
        _format_templates_for_router(),
        format_roster_for_router(roster_agents),
    ])

    # Call Haiku (TDD-03 Section 3.1).
    try:
        parsed = await _call_haiku(user_message)
    except Exception:
        logger.exception("Haiku router call failed")
        return _build_fallback_result(roster_agents, "Haiku API call failed")

    # Validate the response (TDD-03 Section 3.5, step 1).
    validation_errors = _validate_haiku_response(parsed, agent_id_set)
    if validation_errors:
        logger.warning(
            "Haiku response failed validation: %s", validation_errors
        )
        return _build_fallback_result(
            roster_agents,
            f"Invalid Haiku response: {'; '.join(validation_errors)}",
        )

    # Post-process (TDD-03 Section 3.5, steps 2-5).
    template_id: str = parsed["template_id"]
    template = get_template(template_id)
    slot_assignments: dict[str, dict[str, str | None]] = parsed["slot_assignments"]
    reasoning: str = parsed.get("reasoning", "")

    # Enforce lead/worker role constraints (substitute any mismatches).
    slot_assignments, enforcement_warnings = _enforce_lead_assignments(
        slot_assignments, template, eligible
    )
    if enforcement_warnings:
        logger.info("Lead-slot enforcement applied: %s", enforcement_warnings)

    dag_plan = _build_dag_plan(template, slot_assignments)
    assembled_team = _build_assembled_team(slot_assignments)
    step_labels = _build_step_labels(template)

    # Determine dominant model tier for cost estimation.
    model_tier = _dominant_model_tier(slot_assignments, eligible)
    estimated_cost = estimate_cost(template, model_tier)

    # Readiness + enforcement warnings.
    warnings = _readiness_warnings(slot_assignments, eligible) + enforcement_warnings

    return RoutingResult(
        template_key=template_id,
        dag_plan=dag_plan,
        assembled_team=assembled_team,
        step_labels=step_labels,
        estimated_cost=estimated_cost,
        reasoning=reasoning,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Haiku API call
# ---------------------------------------------------------------------------


async def _call_haiku(user_message: str) -> dict[str, Any]:
    """Send a single Haiku call and parse the JSON response.

    Raises on API errors.  Returns a parsed dict on success.
    Raises ``ValueError`` if the response is not valid JSON.
    """
    client = get_anthropic_client()
    response = await client.messages.create(
        model=settings.MODEL_HAIKU,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract text from the response.
    text_parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    raw_text: str = "\n".join(text_parts).strip()
    if not raw_text:
        raise ValueError("Empty response from Haiku")

    # Strip markdown code fences if present (defensive — prompt says no markdown).
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Remove first and last lines if they are fences.
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    try:
        parsed: dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Haiku returned invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Haiku returned {type(parsed).__name__}, expected dict")

    return parsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dominant_model_tier(
    slot_assignments: dict[str, dict[str, str | None]],
    agents: list[RosterAgent],
) -> str:
    """Determine the most common model tier among assigned agents.

    Falls back to ``"sonnet"`` if no agents are assigned.
    """
    agent_lookup: dict[str, RosterAgent] = {a.id: a for a in agents}
    tiers: list[str] = []
    for assignment in slot_assignments.values():
        agent_id = assignment.get("agent_id")
        if agent_id and agent_id in agent_lookup:
            tiers.append(agent_lookup[agent_id].model_tier)
    if not tiers:
        return "sonnet"
    # Most common tier wins.
    return max(set(tiers), key=tiers.count)


def _readiness_warnings(
    slot_assignments: dict[str, dict[str, str | None]],
    agents: list[RosterAgent],
) -> list[str]:
    """Generate warnings for agents with low readiness scores.

    Agents that passed the gate (>= 50) but are below 80 get a warning
    (TDD-03 Section 3.5, step 5: "surface a warning but don't block").
    """
    agent_lookup: dict[str, RosterAgent] = {a.id: a for a in agents}
    warnings: list[str] = []
    for slot_id, assignment in slot_assignments.items():
        agent_id = assignment.get("agent_id")
        if agent_id and agent_id in agent_lookup:
            agent = agent_lookup[agent_id]
            if agent.readiness_score < 80:
                warnings.append(
                    f"Agent {agent.name!r} assigned to slot {slot_id!r} "
                    f"has readiness score {agent.readiness_score} (< 80)"
                )
    return warnings
