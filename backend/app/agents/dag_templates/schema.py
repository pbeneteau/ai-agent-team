"""DAG template schema — dataclasses for execution plan blueprints.

Ref: TDD-03 Section 2.2 (template schema),
     TDD-03 Section 2.1 (concept).

Templates are frozen dataclasses (immutable after construction).  The router
(Ticket 4.2) reads ``DagTemplate.description`` and ``suggested_specializations``
to select and populate templates.  The orchestrator (Ticket 4.3) iterates
waves sequentially and slots within each wave concurrently.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DagSlot:
    """A role in the DAG that will be filled by a roster agent."""

    slot_id: str
    """Unique key within the template (e.g., ``"product_spec"``)."""

    label: str
    """Human-readable name (e.g., ``"Product Specification"``)."""

    role_prompt: str
    """Instructions for the agent filling this slot."""

    suggested_specializations: tuple[str, ...]
    """Roster matching hints (e.g., ``("Product Expert", "Product Manager")``)."""


@dataclass(frozen=True)
class DagWave:
    """A parallel execution stage — all slots run concurrently."""

    wave_number: int
    """1-indexed sequential position within the template."""

    label: str
    """Heartbeat UI label (e.g., ``"Researching competitors..."``).."""

    slots: tuple[DagSlot, ...]
    """Agents to run in parallel within this wave."""

    depends_on: tuple[str, ...]
    """``slot_id``s from previous waves whose output this wave receives."""


@dataclass(frozen=True)
class DagTemplate:
    """A predefined execution plan — the blueprint the orchestrator follows."""

    template_id: str
    """Unique key (e.g., ``"code_feature"``).  Used as registry lookup key."""

    name: str
    """Human-readable name (e.g., ``"Code Feature Build"``)."""

    description: str
    """For the router LLM — describes *when* to pick this template."""

    artifact_type: str
    """``"prose"``, ``"code"``, or ``"both"``."""

    waves: tuple[DagWave, ...]
    """Ordered sequence of execution waves."""

    needs_compile: bool
    """Whether to append a final compile wave for merging parallel outputs."""

    compile_slot: DagSlot | None
    """If ``needs_compile``, the compiler agent slot definition."""

    required_roles: frozenset[str]
    """Union of all ``suggested_specializations`` across every slot.

    Derived from the template's slots — used by the router for roster
    matching and validation.
    """
