"""DAG template registry — 5 MVP execution plan templates.

Ref: TDD-03 Section 2.1-2.3 (template concept, schema, definitions),
     TDD-03 Section 2.4 (registry pattern).

Usage::

    from app.agents.dag_templates import get_template, TEMPLATE_REGISTRY

    template = get_template("code_feature")
    for wave in template.waves:
        for slot in wave.slots:
            print(slot.slot_id, slot.suggested_specializations)
"""

from __future__ import annotations

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave
from app.agents.dag_templates.code_bugfix import CODE_BUGFIX_TEMPLATE
from app.agents.dag_templates.code_feature import CODE_FEATURE_TEMPLATE
from app.agents.dag_templates.content_research import CONTENT_RESEARCH_TEMPLATE
from app.agents.dag_templates.multi_research import MULTI_RESEARCH_TEMPLATE
from app.agents.dag_templates.simple_prose import SIMPLE_PROSE_TEMPLATE

__all__ = [
    "DagSlot",
    "DagWave",
    "DagTemplate",
    "TEMPLATE_REGISTRY",
    "get_template",
    "validate_template",
    "CODE_BUGFIX_TEMPLATE",
    "CODE_FEATURE_TEMPLATE",
    "CONTENT_RESEARCH_TEMPLATE",
    "MULTI_RESEARCH_TEMPLATE",
    "SIMPLE_PROSE_TEMPLATE",
]

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TEMPLATE_REGISTRY: dict[str, DagTemplate] = {
    CODE_FEATURE_TEMPLATE.template_id: CODE_FEATURE_TEMPLATE,
    CONTENT_RESEARCH_TEMPLATE.template_id: CONTENT_RESEARCH_TEMPLATE,
    SIMPLE_PROSE_TEMPLATE.template_id: SIMPLE_PROSE_TEMPLATE,
    CODE_BUGFIX_TEMPLATE.template_id: CODE_BUGFIX_TEMPLATE,
    MULTI_RESEARCH_TEMPLATE.template_id: MULTI_RESEARCH_TEMPLATE,
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
        # Compile slot is conceptually after all waves.
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

    if template.required_roles != actual_roles:
        missing = actual_roles - template.required_roles
        extra = template.required_roles - actual_roles
        if missing:
            errors.append(
                f"required_roles missing: {missing}"
            )
        if extra:
            errors.append(
                f"required_roles has extra entries not in any slot: {extra}"
            )

    # 5. Wave numbering.
    expected = 1
    for wave in template.waves:
        if wave.wave_number != expected:
            errors.append(
                f"Expected wave_number {expected}, got {wave.wave_number}"
            )
        expected += 1

    return errors
