"""DAG template registry — 13 code-focused execution plan templates.

All templates follow a lead-guided structure:
  - Planning wave(s): lead agents analyze the brief and produce delegation plans
  - Execution wave(s): specialist agents implement their delegated tasks
  - Review wave: lead agents evaluate outputs and decide APPROVE / MINOR_FIX / REVISE

Usage::

    from app.agents.dag_templates import get_template, TEMPLATE_REGISTRY

    template = get_template("full_feature")
    for wave in template.waves:
        print(wave.wave_type, [(s.slot_id, s.is_lead) for s in wave.slots])
"""

from __future__ import annotations

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave
from app.agents.dag_templates.full_feature import FULL_FEATURE_TEMPLATE
from app.agents.dag_templates.backend_feature import BACKEND_FEATURE_TEMPLATE
from app.agents.dag_templates.frontend_feature import FRONTEND_FEATURE_TEMPLATE
from app.agents.dag_templates.bug_fix import BUG_FIX_TEMPLATE
from app.agents.dag_templates.refactor import REFACTOR_TEMPLATE
from app.agents.dag_templates.security_fix import SECURITY_FIX_TEMPLATE
from app.agents.dag_templates.performance import PERFORMANCE_TEMPLATE
from app.agents.dag_templates.infra_devops import INFRA_DEVOPS_TEMPLATE
from app.agents.dag_templates.mobile_feature import MOBILE_FEATURE_TEMPLATE
from app.agents.dag_templates.data_feature import DATA_FEATURE_TEMPLATE
from app.agents.dag_templates.api_integration import API_INTEGRATION_TEMPLATE
from app.agents.dag_templates.architecture import ARCHITECTURE_TEMPLATE
from app.agents.dag_templates.design_system import DESIGN_SYSTEM_TEMPLATE

__all__ = [
    "DagSlot",
    "DagWave",
    "DagTemplate",
    "TEMPLATE_REGISTRY",
    "get_template",
    "validate_template",
    # Templates
    "FULL_FEATURE_TEMPLATE",
    "BACKEND_FEATURE_TEMPLATE",
    "FRONTEND_FEATURE_TEMPLATE",
    "BUG_FIX_TEMPLATE",
    "REFACTOR_TEMPLATE",
    "SECURITY_FIX_TEMPLATE",
    "PERFORMANCE_TEMPLATE",
    "INFRA_DEVOPS_TEMPLATE",
    "MOBILE_FEATURE_TEMPLATE",
    "DATA_FEATURE_TEMPLATE",
    "API_INTEGRATION_TEMPLATE",
    "ARCHITECTURE_TEMPLATE",
    "DESIGN_SYSTEM_TEMPLATE",
]

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TEMPLATE_REGISTRY: dict[str, DagTemplate] = {
    FULL_FEATURE_TEMPLATE.template_id:      FULL_FEATURE_TEMPLATE,
    BACKEND_FEATURE_TEMPLATE.template_id:   BACKEND_FEATURE_TEMPLATE,
    FRONTEND_FEATURE_TEMPLATE.template_id:  FRONTEND_FEATURE_TEMPLATE,
    BUG_FIX_TEMPLATE.template_id:           BUG_FIX_TEMPLATE,
    REFACTOR_TEMPLATE.template_id:          REFACTOR_TEMPLATE,
    SECURITY_FIX_TEMPLATE.template_id:      SECURITY_FIX_TEMPLATE,
    PERFORMANCE_TEMPLATE.template_id:       PERFORMANCE_TEMPLATE,
    INFRA_DEVOPS_TEMPLATE.template_id:      INFRA_DEVOPS_TEMPLATE,
    MOBILE_FEATURE_TEMPLATE.template_id:    MOBILE_FEATURE_TEMPLATE,
    DATA_FEATURE_TEMPLATE.template_id:      DATA_FEATURE_TEMPLATE,
    API_INTEGRATION_TEMPLATE.template_id:   API_INTEGRATION_TEMPLATE,
    ARCHITECTURE_TEMPLATE.template_id:      ARCHITECTURE_TEMPLATE,
    DESIGN_SYSTEM_TEMPLATE.template_id:     DESIGN_SYSTEM_TEMPLATE,
}


def get_template(template_key: str) -> DagTemplate:
    """Look up a template by its ``template_id``.

    Raises ``KeyError`` with a descriptive message listing valid keys when
    the requested template does not exist.
    """
    try:
        return TEMPLATE_REGISTRY[template_key]
    except KeyError:
        valid = ", ".join(sorted(TEMPLATE_REGISTRY))
        raise KeyError(
            f"Unknown DAG template {template_key!r}. "
            f"Valid templates: {valid}"
        ) from None


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------

def validate_template(template: DagTemplate) -> list[str]:
    """Validate internal consistency of a ``DagTemplate``.

    Returns an empty list if the template is valid.  Otherwise returns a list
    of human-readable error strings describing every issue found.

    Checks performed:

    1. No duplicate ``slot_id`` values within the template.
    2. Every ``depends_on`` entry references an existing ``slot_id``.
    3. Slots in a wave only depend on slots from *previous* waves (not the
       same wave or a later wave).
    4. ``required_roles`` matches the union of all ``suggested_specializations``
       across every slot (including ``compile_slot`` if present).
    5. Wave numbers are sequential starting from 1.
    6. Every template has exactly one review wave (``wave_type == "review"``).
    7. Planning waves (if any) come before execution waves.
    8. Lead slots (``is_lead=True``) only appear in planning or review waves.
    """
    errors: list[str] = []

    # Collect all slots and build lookup structures.
    all_slot_ids: list[str] = []
    slot_to_wave: dict[str, int] = {}

    for wave in template.waves:
        for slot in wave.slots:
            all_slot_ids.append(slot.slot_id)
            slot_to_wave[slot.slot_id] = wave.wave_number

    if template.compile_slot is not None:
        all_slot_ids.append(template.compile_slot.slot_id)
        compile_wave = max((w.wave_number for w in template.waves), default=0) + 1
        slot_to_wave[template.compile_slot.slot_id] = compile_wave

    # 1. Duplicate slot IDs.
    seen: set[str] = set()
    for sid in all_slot_ids:
        if sid in seen:
            errors.append(f"Duplicate slot_id: {sid!r}")
        seen.add(sid)

    all_slot_id_set = set(all_slot_ids)

    # 2 & 3. depends_on validation.
    for wave in template.waves:
        for dep in wave.depends_on:
            if dep not in all_slot_id_set:
                errors.append(
                    f"Wave {wave.wave_number} ({wave.label!r}) depends_on "
                    f"non-existent slot {dep!r}"
                )
            elif slot_to_wave[dep] >= wave.wave_number:
                errors.append(
                    f"Wave {wave.wave_number} ({wave.label!r}) depends_on "
                    f"slot {dep!r} from wave {slot_to_wave[dep]} "
                    f"(must be from a previous wave)"
                )

    # 4. required_roles consistency.
    actual_roles: set[str] = set()
    for wave in template.waves:
        for slot in wave.slots:
            actual_roles.update(slot.suggested_specializations)
    if template.compile_slot is not None:
        actual_roles.update(template.compile_slot.suggested_specializations)
    if template.validation_wave is not None:
        for slot in template.validation_wave.slots:
            actual_roles.update(slot.suggested_specializations)

    if template.required_roles != actual_roles:
        missing = actual_roles - template.required_roles
        extra = template.required_roles - actual_roles
        if missing:
            errors.append(f"required_roles missing: {missing}")
        if extra:
            errors.append(f"required_roles has extra entries not in any slot: {extra}")

    # 5. Wave numbering.
    expected = 1
    for wave in template.waves:
        if wave.wave_number != expected:
            errors.append(
                f"Expected wave_number {expected}, got {wave.wave_number}"
            )
        expected += 1

    # 6. Exactly one review wave.
    review_waves = [w for w in template.waves if w.wave_type == "review"]
    if len(review_waves) != 1:
        errors.append(
            f"Template must have exactly 1 review wave, found {len(review_waves)}"
        )

    # 7. Planning waves before execution waves.
    wave_types = [w.wave_type for w in template.waves]
    seen_execution = False
    for i, wt in enumerate(wave_types):
        if wt == "execution":
            seen_execution = True
        if wt == "planning" and seen_execution:
            errors.append(
                f"Wave {i + 1}: planning wave found after an execution wave"
            )

    # 8. Lead slots only in planning or review waves.
    for wave in template.waves:
        for slot in wave.slots:
            if slot.is_lead and wave.wave_type == "execution":
                errors.append(
                    f"Slot {slot.slot_id!r} is marked is_lead=True but is in "
                    f"an execution wave (wave {wave.wave_number})"
                )

    return errors
