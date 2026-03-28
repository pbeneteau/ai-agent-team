"""Tests for DAG template library — Ticket 4.1 verification.

Checks:
  - All 5 templates are registered.
  - Each template passes validate_template() (no structural errors).
  - get_template() works for valid keys and raises for unknown keys.
  - required_roles matches actual slot specializations on every template.
  - Wave/slot counts match TDD-03 Section 2.3 specifications.
  - depends_on references only slots from previous waves.
"""

import pytest

from app.agents.dag_templates import (
    TEMPLATE_REGISTRY,
    get_template,
    validate_template,
    CODE_FEATURE_TEMPLATE,
    CONTENT_RESEARCH_TEMPLATE,
    SIMPLE_PROSE_TEMPLATE,
    CODE_BUGFIX_TEMPLATE,
    MULTI_RESEARCH_TEMPLATE,
)


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

def test_registry_has_five_templates():
    assert len(TEMPLATE_REGISTRY) == 5


def test_registry_keys():
    expected = {
        "code_feature",
        "content_research",
        "simple_prose",
        "code_bugfix",
        "multi_research",
    }
    assert set(TEMPLATE_REGISTRY.keys()) == expected


# ---------------------------------------------------------------------------
# get_template tests
# ---------------------------------------------------------------------------

def test_get_template_code_feature():
    t = get_template("code_feature")
    assert t is CODE_FEATURE_TEMPLATE
    assert t.template_id == "code_feature"
    assert len(t.waves) == 3


def test_get_template_content_research():
    t = get_template("content_research")
    assert t is CONTENT_RESEARCH_TEMPLATE
    assert len(t.waves) == 3


def test_get_template_simple_prose():
    t = get_template("simple_prose")
    assert t is SIMPLE_PROSE_TEMPLATE
    assert len(t.waves) == 2


def test_get_template_code_bugfix():
    t = get_template("code_bugfix")
    assert t is CODE_BUGFIX_TEMPLATE
    assert len(t.waves) == 3


def test_get_template_multi_research():
    t = get_template("multi_research")
    assert t is MULTI_RESEARCH_TEMPLATE
    assert len(t.waves) == 2


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
# Structural validation — every template must pass
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template_id", list(TEMPLATE_REGISTRY.keys()))
def test_validate_template_passes(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    errors = validate_template(template)
    assert errors == [], f"Validation errors for {template_id}: {errors}"


# ---------------------------------------------------------------------------
# required_roles matches actual slot specializations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template_id", list(TEMPLATE_REGISTRY.keys()))
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
# Slot counts per template (TDD-03 Section 2.3)
# ---------------------------------------------------------------------------

def test_code_feature_slot_count():
    total = sum(len(w.slots) for w in CODE_FEATURE_TEMPLATE.waves)
    assert total == 4  # product_spec, design_spec, implementation, qa_review


def test_content_research_slot_count():
    total = sum(len(w.slots) for w in CONTENT_RESEARCH_TEMPLATE.waves)
    assert total == 4  # researcher, framework_designer, writer, editor


def test_simple_prose_slot_count():
    total = sum(len(w.slots) for w in SIMPLE_PROSE_TEMPLATE.waves)
    assert total == 2  # writer, editor


def test_code_bugfix_slot_count():
    total = sum(len(w.slots) for w in CODE_BUGFIX_TEMPLATE.waves)
    assert total == 3  # analyst, fixer, validator


def test_multi_research_slot_count():
    total = sum(len(w.slots) for w in MULTI_RESEARCH_TEMPLATE.waves)
    assert total == 3  # researcher_a, researcher_b, compiler


# ---------------------------------------------------------------------------
# Specific slot IDs exist
# ---------------------------------------------------------------------------

def test_code_feature_slot_ids():
    slot_ids = {s.slot_id for w in CODE_FEATURE_TEMPLATE.waves for s in w.slots}
    assert slot_ids == {"product_spec", "design_spec", "implementation", "qa_review"}


def test_code_feature_dependency_graph():
    """Wave 1: no deps.  Wave 2: depends on wave 1.  Wave 3: depends on 1+2."""
    w1, w2, w3 = CODE_FEATURE_TEMPLATE.waves
    assert w1.depends_on == ()
    assert set(w2.depends_on) == {"product_spec", "design_spec"}
    assert set(w3.depends_on) == {"product_spec", "design_spec", "implementation"}


def test_multi_research_dependency_graph():
    """Wave 1: no deps.  Wave 2: depends on both researchers."""
    w1, w2 = MULTI_RESEARCH_TEMPLATE.waves
    assert w1.depends_on == ()
    assert set(w2.depends_on) == {"researcher_a", "researcher_b"}


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

def test_templates_are_frozen():
    with pytest.raises(AttributeError):
        CODE_FEATURE_TEMPLATE.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# needs_compile is False for all MVP templates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template_id", list(TEMPLATE_REGISTRY.keys()))
def test_needs_compile_false(template_id):
    template = TEMPLATE_REGISTRY[template_id]
    assert template.needs_compile is False
    assert template.compile_slot is None
