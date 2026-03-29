"""DAG template schema — dataclasses for execution plan blueprints.

Ref: TDD-03 Section 2.2 (template schema),
     TDD-03 Section 2.1 (concept).

Templates are frozen dataclasses (immutable after construction).  The router
reads ``DagTemplate.description`` and ``suggested_specializations`` to select
and populate templates.  The orchestrator iterates waves sequentially and slots
within each wave concurrently.

Wave types:
  - ``"planning"``: Lead agents analyze the brief and produce a structured
    delegation plan for the specialists in the next execution wave.
  - ``"validation"``: Lead agents validate the delegation plan before
    execution begins.  Runs between planning and execution (Ticket 17.3).
  - ``"execution"``: Specialist agents execute their delegated tasks.
  - ``"review"``: Lead agents evaluate all outputs and decide to APPROVE,
    MINOR_FIX (fix directly), or REVISE (send back with notes).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DagSlot:
    """A role in the DAG that will be filled by a roster agent."""

    slot_id: str
    """Unique key within the template (e.g., ``"tech_plan"``)."""

    label: str
    """Human-readable name (e.g., ``"Tech Lead Planning"``)."""

    role_prompt: str
    """Instructions for the agent filling this slot."""

    suggested_specializations: tuple[str, ...]
    """Roster matching hints (e.g., ``("Tech Lead", "Engineering Manager")``)."""

    is_lead: bool = False
    """True for lead agents (planning/review), False for specialist workers."""


@dataclass(frozen=True)
class DagWave:
    """A parallel execution stage — all slots run concurrently."""

    wave_number: int
    """1-indexed sequential position within the template."""

    label: str
    """Heartbeat UI label (e.g., ``"Tech Lead planning..."``).."""

    slots: tuple[DagSlot, ...]
    """Agents to run in parallel within this wave."""

    depends_on: tuple[str, ...]
    """``slot_id``s from previous waves whose output this wave receives."""

    wave_type: str = "execution"
    """``"planning"`` | ``"execution"`` | ``"review"``."""


@dataclass(frozen=True)
class DagTemplate:
    """A predefined execution plan — the blueprint the orchestrator follows."""

    template_id: str
    """Unique key (e.g., ``"full_feature"``).  Used as registry lookup key."""

    name: str
    """Human-readable name (e.g., ``"Full Product Feature"``)."""

    description: str
    """For the router LLM — describes *when* to pick this template."""

    artifact_type: str
    """``"code"`` for all code-focused templates."""

    waves: tuple[DagWave, ...]
    """Ordered sequence of execution waves."""

    needs_compile: bool
    """Whether to append a final compile wave for merging parallel outputs."""

    compile_slot: DagSlot | None
    """If ``needs_compile``, the compiler agent slot definition."""

    required_roles: frozenset[str]
    """Union of all ``suggested_specializations`` across every slot.

    Used by the router for roster matching and validation.
    """

    review_criteria: tuple[str, ...] = ()
    """Template-specific grading criteria for review leads.

    Each entry is a natural-language criterion the review lead must explicitly
    grade as PASS or FAIL.  Injected into the review prompt by the orchestrator
    (Ticket 17.2, AD-26).  Empty tuple means no structured criteria.
    """

    validation_wave: DagWave | None = None
    """Optional wave that validates the delegation plan before execution begins.

    Runs between planning and execution.  Uses ``wave_type="validation"``.
    If the validator decides REVISE, planning waves re-run once with feedback.
    Only enabled on complex templates where vague delegation is costly
    (Ticket 17.3, AD-27).  ``None`` means no validation step.
    """

    max_iterations: int = 3
    """Maximum review-revise cycles before the lead force-approves."""
