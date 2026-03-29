"""Tests for DAG template library — Sprint 13 lead-guided templates.

Checks:
  - All 13 templates are registered.
  - Each template passes validate_template() (no structural errors).
  - get_template() works for valid keys and raises for unknown keys.
  - required_roles matches actual slot specializations on every template.
  - All templates have exactly one review wave.
  - Lead slots (is_lead=True) appear only in planning or review waves.
  - max_iterations is set on every template.
  - needs_compile is False for all templates.
"""

import pytest

from app.agents.dag_templates import (
    TEMPLATE_REGISTRY,
    get_template,
    validate_template,
    FULL_FEATURE_TEMPLATE,
    BACKEND_FEATURE_TEMPLATE,
    FRONTEND_FEATURE_TEMPLATE,
    BUG_FIX_TEMPLATE,
    REFACTOR_TEMPLATE,
    SECURITY_FIX_TEMPLATE,
    PERFORMANCE_TEMPLATE,
    INFRA_DEVOPS_TEMPLATE,
    MOBILE_FEATURE_TEMPLATE,
    DATA_FEATURE_TEMPLATE,
    API_INTEGRATION_TEMPLATE,
    ARCHITECTURE_TEMPLATE,
    DESIGN_SYSTEM_TEMPLATE,
)

# All 13 template IDs
ALL_TEMPLATE_IDS = [
    "full_feature",
    "backend_feature",
    "frontend_feature",
    "bug_fix",
    "refactor",
    "security_fix",
    "performance",
    "infra_devops",
    "mobile_feature",
    "data_feature",
    "api_integration",
    "architecture",
    "design_system",
]


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_registry_has_thirteen_templates():
    assert len(TEMPLATE_REGISTRY) == 13


def test_registry_keys():
    assert set(TEMPLATE_REGISTRY.keys()) == set(ALL_TEMPLATE_IDS)


# ---------------------------------------------------------------------------
# get_template tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_get_template_returns_correct_template(template_id):
    t = get_template(template_id)
    assert t.template_id == template_id


def test_get_template_bug_fix_is_imported():
    t = get_template("bug_fix")
    assert t is BUG_FIX_TEMPLATE


def test_get_template_full_feature_is_imported():
    t = get_template("full_feature")
    assert t is FULL_FEATURE_TEMPLATE


def test_get_template_unknown_raises():
    with pytest.raises(KeyError, match="Unknown DAG template 'unknown'"):
        get_template("unknown")


def test_get_template_error_lists_valid_keys():
    with pytest.raises(KeyError) as exc_info:
        get_template("nonexistent")
    msg = str(exc_info.value)
    for key in TEMPLATE_REGISTRY:
        assert key in msg


# ---------------------------------------------------------------------------
# Structural validation — every template must pass validate_template()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_validate_template_passes(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    errors = validate_template(template)
    assert errors == [], f"Validation errors for {template_id}: {errors}"


# ---------------------------------------------------------------------------
# required_roles matches actual slot specializations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_required_roles_matches_slots(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    actual: set[str] = set()
    for wave in template.waves:
        for slot in wave.slots:
            actual.update(slot.suggested_specializations)
    if template.compile_slot is not None:
        actual.update(template.compile_slot.suggested_specializations)
    assert template.required_roles == actual


# ---------------------------------------------------------------------------
# Lead structure invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_exactly_one_review_wave(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    review_waves = [w for w in template.waves if w.wave_type == "review"]
    assert len(review_waves) == 1, (
        f"{template_id}: expected 1 review wave, got {len(review_waves)}"
    )


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_lead_slots_only_in_planning_or_review(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    for wave in template.waves:
        for slot in wave.slots:
            if slot.is_lead:
                assert wave.wave_type in ("planning", "review"), (
                    f"{template_id}: slot '{slot.slot_id}' is_lead=True but wave_type={wave.wave_type!r}"
                )


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_at_least_one_lead_slot(template_id):
    """Every template must have at least one lead (planning or review lead)."""
    template = TEMPLATE_REGISTRY[template_id]
    lead_slots = [
        slot for wave in template.waves for slot in wave.slots if slot.is_lead
    ]
    assert len(lead_slots) >= 1, f"{template_id}: no lead slots found"


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_at_least_one_execution_wave(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    execution_waves = [w for w in template.waves if w.wave_type == "execution"]
    assert len(execution_waves) >= 1, f"{template_id}: no execution wave found"


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_planning_before_execution(template_id):
    """All planning waves must come before execution waves."""
    template = TEMPLATE_REGISTRY[template_id]
    seen_execution = False
    for wave in template.waves:
        if wave.wave_type == "execution":
            seen_execution = True
        if wave.wave_type == "planning":
            assert not seen_execution, (
                f"{template_id}: planning wave found after execution wave at wave {wave.wave_number}"
            )


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_review_wave_is_last(template_id):
    """The review wave must be the final wave in every template."""
    template = TEMPLATE_REGISTRY[template_id]
    last_wave = template.waves[-1]
    assert last_wave.wave_type == "review", (
        f"{template_id}: last wave is {last_wave.wave_type!r}, expected 'review'"
    )


# ---------------------------------------------------------------------------
# max_iterations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_max_iterations_positive(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    assert template.max_iterations >= 1, f"{template_id}: max_iterations must be >= 1"


def test_bug_fix_max_iterations():
    assert BUG_FIX_TEMPLATE.max_iterations == 2


def test_full_feature_max_iterations():
    assert FULL_FEATURE_TEMPLATE.max_iterations == 3


def test_security_fix_max_iterations():
    assert SECURITY_FIX_TEMPLATE.max_iterations == 3


# ---------------------------------------------------------------------------
# Slot counts per key template
# ---------------------------------------------------------------------------


def test_bug_fix_slot_count():
    total = sum(len(w.slots) for w in BUG_FIX_TEMPLATE.waves)
    assert total == 3  # tech_plan, dev, tech_review


def test_bug_fix_slot_ids():
    slot_ids = {s.slot_id for w in BUG_FIX_TEMPLATE.waves for s in w.slots}
    assert slot_ids == {"tech_plan", "dev_impl", "tech_review"}


def test_full_feature_slot_count():
    total = sum(len(w.slots) for w in FULL_FEATURE_TEMPLATE.waves)
    assert total == 6  # pm_plan + design_plan + backend_impl + frontend_impl + qa_impl + tech_review


def test_backend_feature_slot_count():
    total = sum(len(w.slots) for w in BACKEND_FEATURE_TEMPLATE.waves)
    assert total == 4  # pm_plan + tech_plan + backend_impl + tech_review


def test_security_fix_has_parallel_review():
    review_wave = next(w for w in SECURITY_FIX_TEMPLATE.waves if w.wave_type == "review")
    assert len(review_wave.slots) == 2  # security_review + tech_review


# ---------------------------------------------------------------------------
# needs_compile is False for all templates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_needs_compile_false(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    assert template.needs_compile is False
    assert template.compile_slot is None


# ---------------------------------------------------------------------------
# Immutability — templates are frozen dataclasses
# ---------------------------------------------------------------------------


def test_templates_are_frozen():
    with pytest.raises((AttributeError, TypeError)):
        BUG_FIX_TEMPLATE.name = "changed"  # type: ignore[misc]


def test_waves_are_tuples():
    """Waves must be tuples (immutable)."""
    assert isinstance(BUG_FIX_TEMPLATE.waves, tuple)


def test_slots_are_tuples():
    for wave in BUG_FIX_TEMPLATE.waves:
        assert isinstance(wave.slots, tuple)


# ---------------------------------------------------------------------------
# Wave type coverage
# ---------------------------------------------------------------------------


def test_all_wave_types_are_valid():
    valid_types = {"planning", "execution", "review"}
    for template_id, template in TEMPLATE_REGISTRY.items():
        for wave in template.waves:
            assert wave.wave_type in valid_types, (
                f"{template_id}: wave {wave.wave_number} has invalid wave_type {wave.wave_type!r}"
            )


# ---------------------------------------------------------------------------
# Review criteria (Ticket 17.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_review_criteria_non_empty(template_id):
    """Every lead-guided template must have at least one review criterion."""
    template = TEMPLATE_REGISTRY[template_id]
    assert len(template.review_criteria) >= 3, (
        f"{template_id}: expected at least 3 review criteria, got {len(template.review_criteria)}"
    )


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_review_criteria_are_strings(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    for criterion in template.review_criteria:
        assert isinstance(criterion, str), (
            f"{template_id}: criterion must be a string, got {type(criterion)}"
        )
        assert len(criterion) > 10, (
            f"{template_id}: criterion too short: {criterion!r}"
        )


@pytest.mark.parametrize("template_id", ALL_TEMPLATE_IDS)
def test_review_criteria_is_tuple(template_id):
    """review_criteria must be a tuple (immutable)."""
    template = TEMPLATE_REGISTRY[template_id]
    assert isinstance(template.review_criteria, tuple)


def test_bug_fix_criteria_mentions_root_cause():
    """Bug fix criteria should check that the root cause is addressed."""
    criteria_text = " ".join(BUG_FIX_TEMPLATE.review_criteria)
    assert "root cause" in criteria_text.lower()


def test_security_fix_criteria_mentions_vulnerability():
    """Security fix criteria should check that the vulnerability is mitigated."""
    criteria_text = " ".join(SECURITY_FIX_TEMPLATE.review_criteria)
    assert "vulnerab" in criteria_text.lower() or "attack" in criteria_text.lower()


# ---------------------------------------------------------------------------
# Delegation validation waves (Ticket 17.3)
# ---------------------------------------------------------------------------

_TEMPLATES_WITH_VALIDATION = ["full_feature", "architecture", "api_integration", "data_feature"]
_TEMPLATES_WITHOUT_VALIDATION = [
    tid for tid in ALL_TEMPLATE_IDS if tid not in _TEMPLATES_WITH_VALIDATION
]


@pytest.mark.parametrize("template_id", _TEMPLATES_WITH_VALIDATION)
def test_complex_templates_have_validation_wave(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    assert template.validation_wave is not None, (
        f"{template_id}: expected a validation_wave, got None"
    )
    assert template.validation_wave.wave_type == "validation"


@pytest.mark.parametrize("template_id", _TEMPLATES_WITHOUT_VALIDATION)
def test_simple_templates_have_no_validation_wave(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    assert template.validation_wave is None, (
        f"{template_id}: should not have a validation_wave"
    )


@pytest.mark.parametrize("template_id", _TEMPLATES_WITH_VALIDATION)
def test_validation_wave_has_lead_slot(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    vw = template.validation_wave
    assert len(vw.slots) >= 1
    assert all(s.is_lead for s in vw.slots), (
        f"{template_id}: validation slots must be is_lead=True"
    )


@pytest.mark.parametrize("template_id", _TEMPLATES_WITH_VALIDATION)
def test_validation_wave_depends_on_planning_slots(template_id):
    """Validation wave must depend on planning slot IDs that actually exist."""
    template = TEMPLATE_REGISTRY[template_id]
    planning_slot_ids = {
        s.slot_id
        for w in template.waves if w.wave_type == "planning"
        for s in w.slots
    }
    for dep in template.validation_wave.depends_on:
        assert dep in planning_slot_ids, (
            f"{template_id}: validation depends_on {dep!r} but that's not a planning slot"
        )


@pytest.mark.parametrize("template_id", _TEMPLATES_WITH_VALIDATION)
def test_validation_wave_specializations_in_required_roles(template_id):
    """Validation slot specializations must be covered by the template's required_roles."""
    template = TEMPLATE_REGISTRY[template_id]
    for slot in template.validation_wave.slots:
        for spec in slot.suggested_specializations:
            assert spec in template.required_roles, (
                f"{template_id}: validation spec {spec!r} not in required_roles"
            )
