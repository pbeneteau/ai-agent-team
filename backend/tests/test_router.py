"""Tests for auto-assembly & DAG router — Ticket 4.2 verification.

Checks:
  - Mock Haiku response → dag_plan JSONB correctly hydrated.
  - estimate_cost("code_feature", "sonnet") returns correct Decimal.
  - Invalid JSON from Haiku → fallback to simple_prose.
  - Unknown template_id in Haiku response → fallback.
  - Unknown agent_id in Haiku response → fallback.
  - Agents below readiness gate excluded from roster.
  - Fallback picks highest-readiness agent.
  - Parallel conflict detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.router import (
    READINESS_GATE,
    RoutingResult,
    _build_dag_plan,
    _build_assembled_team,
    _build_fallback_result,
    _build_step_labels,
    _filter_eligible_agents,
    _validate_haiku_response,
    estimate_cost,
    format_brief_for_router,
    format_roster_for_router,
    route_brief,
)
from app.agents.dag_templates import get_template


# ---------------------------------------------------------------------------
# Test fixtures — lightweight mock objects
# ---------------------------------------------------------------------------


@dataclass
class MockArtifact:
    title: str = "Settings Page"
    artifact_type: str = "code"
    goal: str | None = "Build a user settings page"
    target_audience: str | None = "End users"
    context: str | None = "React + Tailwind stack"
    description: str | None = "A settings page with profile, notifications, and theme preferences."


@dataclass
class MockAgent:
    id: str = "agent-1"
    name: str = "Frontend Dev"
    specialization: str = "Frontend development with React"
    readiness_score: int = 80
    progression_level: str = "opérationnel"
    model_tier: str = "sonnet"
    status: str = "ready"
    archived_at: datetime | None = None


def _make_agents() -> list[MockAgent]:
    """Standard 4-agent roster for tests."""
    return [
        MockAgent(id="agent-product", name="Product Expert", specialization="Product management", readiness_score=90),
        MockAgent(id="agent-design", name="Design Expert", specialization="UX/UI design", readiness_score=85),
        MockAgent(id="agent-frontend", name="Frontend Dev", specialization="React development", readiness_score=80),
        MockAgent(id="agent-qa", name="QA Engineer", specialization="Quality assurance", readiness_score=75),
    ]


def _valid_haiku_response() -> dict[str, Any]:
    """Standard valid Haiku response for code_feature template."""
    return {
        "template_id": "code_feature",
        "reasoning": "Brief asks to build a settings page — this is a code feature.",
        "slot_assignments": {
            "product_spec": {"agent_id": "agent-product", "agent_name": "Product Expert"},
            "design_spec": {"agent_id": "agent-design", "agent_name": "Design Expert"},
            "implementation": {"agent_id": "agent-frontend", "agent_name": "Frontend Dev"},
            "qa_review": {"agent_id": "agent-qa", "agent_name": "QA Engineer"},
        },
        "estimated_waves": 3,
        "estimated_cost_usd": 0.85,
    }


# ---------------------------------------------------------------------------
# Cost estimation tests (TDD-03 Section 3.6)
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_code_feature_sonnet(self):
        template = get_template("code_feature")
        cost = estimate_cost(template, "sonnet")
        # 4 slots × $0.042 = $0.168 → rounds to $0.17
        assert cost == Decimal("0.17")

    def test_code_feature_opus(self):
        template = get_template("code_feature")
        cost = estimate_cost(template, "opus")
        # 4 slots × $0.210 = $0.840 → rounds to $0.84
        assert cost == Decimal("0.84")

    def test_simple_prose_sonnet(self):
        template = get_template("simple_prose")
        cost = estimate_cost(template, "sonnet")
        # 2 slots × $0.042 = $0.084 → rounds to $0.08
        assert cost == Decimal("0.08")

    def test_multi_research_sonnet(self):
        template = get_template("multi_research")
        cost = estimate_cost(template, "sonnet")
        # 3 slots × $0.042 = $0.126 → rounds to $0.13
        assert cost == Decimal("0.13")

    def test_unknown_tier_defaults_to_sonnet(self):
        template = get_template("simple_prose")
        cost = estimate_cost(template, "imaginary_tier")
        assert cost == estimate_cost(template, "sonnet")

    def test_returns_decimal(self):
        template = get_template("code_feature")
        cost = estimate_cost(template, "sonnet")
        assert isinstance(cost, Decimal)


# ---------------------------------------------------------------------------
# Formatting tests
# ---------------------------------------------------------------------------


class TestFormatBrief:
    def test_includes_all_fields(self):
        artifact = MockArtifact()
        text = format_brief_for_router(artifact)
        assert "Settings Page" in text
        assert "code" in text
        assert "Build a user settings page" in text
        assert "End users" in text
        assert "React + Tailwind stack" in text
        assert "profile, notifications" in text

    def test_omits_none_fields(self):
        artifact = MockArtifact(goal=None, target_audience=None)
        text = format_brief_for_router(artifact)
        assert "Goal:" not in text
        assert "Target Audience:" not in text
        assert "Title: Settings Page" in text


class TestFormatRoster:
    def test_includes_eligible_agents(self):
        agents = _make_agents()
        text = format_roster_for_router(agents)
        assert "agent-product" in text
        assert "Product Expert" in text
        assert "readiness: 90" in text

    def test_excludes_below_readiness_gate(self):
        agents = [
            MockAgent(id="low", name="Low Agent", readiness_score=30),
            MockAgent(id="high", name="High Agent", readiness_score=80),
        ]
        text = format_roster_for_router(agents)
        assert "low" not in text
        assert "high" in text

    def test_excludes_archived_agents(self):
        agents = [
            MockAgent(id="archived", name="Old Agent", readiness_score=90, archived_at=datetime.now()),
            MockAgent(id="active", name="Active Agent", readiness_score=80),
        ]
        text = format_roster_for_router(agents)
        assert "archived" not in text
        assert "active" in text


# ---------------------------------------------------------------------------
# Eligibility filter tests
# ---------------------------------------------------------------------------


class TestFilterEligible:
    def test_filters_below_gate(self):
        agents = [
            MockAgent(id="a", readiness_score=49),
            MockAgent(id="b", readiness_score=50),
            MockAgent(id="c", readiness_score=100),
        ]
        eligible = _filter_eligible_agents(agents)
        ids = {a.id for a in eligible}
        assert ids == {"b", "c"}

    def test_filters_archived(self):
        agents = [
            MockAgent(id="a", readiness_score=80, archived_at=datetime.now()),
            MockAgent(id="b", readiness_score=80),
        ]
        eligible = _filter_eligible_agents(agents)
        assert len(eligible) == 1
        assert eligible[0].id == "b"

    def test_readiness_gate_value(self):
        assert READINESS_GATE == 50


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidateHaikuResponse:
    def test_valid_response(self):
        agents = _make_agents()
        agent_ids = {a.id for a in agents}
        errors = _validate_haiku_response(_valid_haiku_response(), agent_ids)
        assert errors == []

    def test_unknown_template(self):
        response = _valid_haiku_response()
        response["template_id"] = "nonexistent"
        errors = _validate_haiku_response(response, set())
        assert any("Unknown template_id" in e for e in errors)

    def test_missing_template_id(self):
        response = _valid_haiku_response()
        del response["template_id"]
        errors = _validate_haiku_response(response, set())
        assert len(errors) > 0

    def test_unknown_agent_id(self):
        response = _valid_haiku_response()
        agent_ids = {"agent-product", "agent-design", "agent-frontend"}  # missing agent-qa
        errors = _validate_haiku_response(response, agent_ids)
        assert any("not in roster" in e for e in errors)

    def test_null_agent_id_is_valid(self):
        response = _valid_haiku_response()
        response["slot_assignments"]["qa_review"]["agent_id"] = None
        agent_ids = {"agent-product", "agent-design", "agent-frontend"}
        errors = _validate_haiku_response(response, agent_ids)
        assert errors == []

    def test_missing_slot_assignments(self):
        response = _valid_haiku_response()
        del response["slot_assignments"]["qa_review"]
        agent_ids = {a.id for a in _make_agents()}
        errors = _validate_haiku_response(response, agent_ids)
        assert any("Missing slot" in e for e in errors)

    def test_parallel_conflict(self):
        response = _valid_haiku_response()
        # Assign same agent to both wave-1 slots (product_spec and design_spec)
        response["slot_assignments"]["design_spec"]["agent_id"] = "agent-product"
        agent_ids = {a.id for a in _make_agents()}
        errors = _validate_haiku_response(response, agent_ids)
        assert any("parallel conflict" in e for e in errors)


# ---------------------------------------------------------------------------
# DAG plan building tests
# ---------------------------------------------------------------------------


class TestBuildDagPlan:
    def test_hydrates_code_feature(self):
        template = get_template("code_feature")
        slot_assignments = _valid_haiku_response()["slot_assignments"]
        plan = _build_dag_plan(template, slot_assignments)

        assert "waves" in plan
        assert len(plan["waves"]) == 3

        wave1 = plan["waves"][0]
        assert wave1["wave_number"] == 1
        assert wave1["label"] == "Defining requirements & design specs"
        assert len(wave1["agents"]) == 2
        assert wave1["agents"][0]["agent_id"] == "agent-product"
        assert wave1["agents"][0]["output_key"] == "product_spec"
        # Wave 1 has no depends_on
        assert "depends_on" not in wave1["agents"][0]

        wave2 = plan["waves"][1]
        assert wave2["wave_number"] == 2
        assert len(wave2["agents"]) == 1
        assert wave2["agents"][0]["agent_id"] == "agent-frontend"
        assert set(wave2["agents"][0]["depends_on"]) == {"product_spec", "design_spec"}

        wave3 = plan["waves"][2]
        assert wave3["agents"][0]["agent_id"] == "agent-qa"
        assert "implementation" in wave3["agents"][0]["depends_on"]


class TestBuildAssembledTeam:
    def test_deduplicates(self):
        # Same agent in two slots
        slot_assignments = {
            "writer": {"agent_id": "agent-1", "agent_name": "Writer"},
            "editor": {"agent_id": "agent-1", "agent_name": "Writer"},
        }
        team = _build_assembled_team(slot_assignments)
        assert len(team) == 1
        assert team[0]["agent_id"] == "agent-1"

    def test_skips_null_agent_id(self):
        slot_assignments = {
            "writer": {"agent_id": "agent-1", "agent_name": "Writer"},
            "editor": {"agent_id": None, "agent_name": "Generic"},
        }
        team = _build_assembled_team(slot_assignments)
        assert len(team) == 1


class TestBuildStepLabels:
    def test_code_feature_labels(self):
        template = get_template("code_feature")
        labels = _build_step_labels(template)
        assert labels == [
            "Defining requirements & design specs",
            "Implementing code",
            "Quality review",
        ]


# ---------------------------------------------------------------------------
# Fallback tests
# ---------------------------------------------------------------------------


class TestFallback:
    def test_uses_simple_prose(self):
        agents = _make_agents()
        result = _build_fallback_result(agents, "test reason")
        assert result.template_key == "simple_prose"
        assert result.is_fallback is True

    def test_picks_highest_readiness_agent(self):
        agents = _make_agents()
        result = _build_fallback_result(agents, "test")
        # agent-product has readiness 90 — highest
        team_ids = {a["agent_id"] for a in result.assembled_team}
        assert "agent-product" in team_ids

    def test_all_slots_filled(self):
        agents = _make_agents()
        result = _build_fallback_result(agents, "test")
        template = get_template("simple_prose")
        plan_agents = [
            agent
            for wave in result.dag_plan["waves"]
            for agent in wave["agents"]
        ]
        expected_slots = sum(len(w.slots) for w in template.waves)
        assert len(plan_agents) == expected_slots

    def test_no_eligible_agents_uses_best_non_archived(self):
        agents = [
            MockAgent(id="low-1", readiness_score=30, name="Low1"),
            MockAgent(id="low-2", readiness_score=40, name="Low2"),
        ]
        result = _build_fallback_result(agents, "test")
        team_ids = {a["agent_id"] for a in result.assembled_team}
        assert "low-2" in team_ids  # highest readiness among non-eligible

    def test_includes_reason_in_reasoning(self):
        result = _build_fallback_result(_make_agents(), "Haiku exploded")
        assert "Haiku exploded" in result.reasoning


# ---------------------------------------------------------------------------
# Integration tests — route_brief with mocked Haiku
# ---------------------------------------------------------------------------


def _mock_haiku_response_message(response_json: dict[str, Any]) -> Any:
    """Create a mock Anthropic messages response."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(response_json)

    message = MagicMock()
    message.content = [text_block]
    return message


import json


class TestRouteBrief:
    @pytest.mark.asyncio
    async def test_valid_haiku_response_hydrates_dag_plan(self):
        artifact = MockArtifact()
        agents = _make_agents()
        haiku_response = _valid_haiku_response()

        with patch(
            "app.agents.router._call_haiku",
            new_callable=AsyncMock,
            return_value=haiku_response,
        ):
            result = await route_brief(artifact, agents)

        assert result.template_key == "code_feature"
        assert result.is_fallback is False
        assert len(result.dag_plan["waves"]) == 3
        assert len(result.assembled_team) == 4
        assert len(result.step_labels) == 3
        assert isinstance(result.estimated_cost, Decimal)
        assert result.reasoning == haiku_response["reasoning"]

    @pytest.mark.asyncio
    async def test_invalid_json_triggers_fallback(self):
        artifact = MockArtifact()
        agents = _make_agents()

        with patch(
            "app.agents.router._call_haiku",
            new_callable=AsyncMock,
            side_effect=ValueError("Haiku returned invalid JSON"),
        ):
            result = await route_brief(artifact, agents)

        assert result.is_fallback is True
        assert result.template_key == "simple_prose"

    @pytest.mark.asyncio
    async def test_unknown_template_triggers_fallback(self):
        artifact = MockArtifact()
        agents = _make_agents()
        bad_response = _valid_haiku_response()
        bad_response["template_id"] = "nonexistent_template"

        with patch(
            "app.agents.router._call_haiku",
            new_callable=AsyncMock,
            return_value=bad_response,
        ):
            result = await route_brief(artifact, agents)

        assert result.is_fallback is True
        assert result.template_key == "simple_prose"

    @pytest.mark.asyncio
    async def test_unknown_agent_id_triggers_fallback(self):
        artifact = MockArtifact()
        agents = _make_agents()
        bad_response = _valid_haiku_response()
        bad_response["slot_assignments"]["qa_review"]["agent_id"] = "nonexistent-agent"

        with patch(
            "app.agents.router._call_haiku",
            new_callable=AsyncMock,
            return_value=bad_response,
        ):
            result = await route_brief(artifact, agents)

        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_api_error_triggers_fallback(self):
        artifact = MockArtifact()
        agents = _make_agents()

        with patch(
            "app.agents.router._call_haiku",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Connection failed"),
        ):
            result = await route_brief(artifact, agents)

        assert result.is_fallback is True
        assert "failed" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_no_eligible_agents_triggers_fallback(self):
        artifact = MockArtifact()
        agents = [MockAgent(id="low", readiness_score=30)]

        result = await route_brief(artifact, agents)

        assert result.is_fallback is True
        assert "readiness gate" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_readiness_warnings_for_partial_agents(self):
        artifact = MockArtifact()
        agents = _make_agents()
        # agent-qa has readiness 75 — below 80, should get a warning
        haiku_response = _valid_haiku_response()

        with patch(
            "app.agents.router._call_haiku",
            new_callable=AsyncMock,
            return_value=haiku_response,
        ):
            result = await route_brief(artifact, agents)

        assert any("QA Engineer" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_dag_plan_structure_matches_tdd02(self):
        """Verify dag_plan matches TDD-02 Section 3.3 JSONB schema."""
        artifact = MockArtifact()
        agents = _make_agents()
        haiku_response = _valid_haiku_response()

        with patch(
            "app.agents.router._call_haiku",
            new_callable=AsyncMock,
            return_value=haiku_response,
        ):
            result = await route_brief(artifact, agents)

        plan = result.dag_plan
        assert "waves" in plan
        for wave in plan["waves"]:
            assert "wave_number" in wave
            assert "label" in wave
            assert "agents" in wave
            for agent in wave["agents"]:
                assert "agent_id" in agent
                assert "role_in_wave" in agent
                assert "output_key" in agent
