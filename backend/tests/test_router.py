"""Tests for auto-assembly & DAG router — Tickets 4.2 + 13.5.

Checks:
  - Mock Haiku response → dag_plan JSONB correctly hydrated.
  - estimate_cost("bug_fix", "sonnet") returns correct Decimal.
  - Invalid JSON from Haiku → fallback to bug_fix.
  - Unknown template_id in Haiku response → fallback.
  - Unknown agent_id in Haiku response → fallback.
  - Agents below readiness gate excluded from roster.
  - Fallback picks lead for lead slots, worker for execution slots.
  - Parallel conflict detection.
  - Lead-slot enforcement: worker agents are substituted with leads for is_lead slots.
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
    _enforce_lead_assignments,
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
    role: str = "worker"
    archived_at: datetime | None = None


def _make_agents() -> list[MockAgent]:
    """Standard roster with leads and workers for tests."""
    return [
        MockAgent(id="agent-tech-lead", name="Tech Lead", specialization="Technical architecture and engineering delegation", readiness_score=90, role="lead"),
        MockAgent(id="agent-pm-lead", name="PM Lead", specialization="Product requirements and team coordination", readiness_score=85, role="lead"),
        MockAgent(id="agent-backend", name="Backend Dev", specialization="Backend APIs and database implementation", readiness_score=80, role="worker"),
        MockAgent(id="agent-frontend", name="Frontend Dev", specialization="React development and UI implementation", readiness_score=75, role="worker"),
    ]


def _valid_haiku_response() -> dict[str, Any]:
    """Standard valid Haiku response for bug_fix template."""
    return {
        "template_id": "bug_fix",
        "reasoning": "Brief asks to fix a bug — this is a bug_fix.",
        "slot_assignments": {
            "tech_plan": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},
            "dev_impl": {"agent_id": "agent-backend", "agent_name": "Backend Dev"},
            "tech_review": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},
        },
    }


# ---------------------------------------------------------------------------
# Cost estimation tests (TDD-03 Section 3.6)
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_bug_fix_sonnet(self):
        template = get_template("bug_fix")
        cost = estimate_cost(template, "sonnet")
        # 3 slots × $0.042 = $0.126 → rounds to $0.13
        assert cost == Decimal("0.13")

    def test_bug_fix_opus(self):
        template = get_template("bug_fix")
        cost = estimate_cost(template, "opus")
        # 3 slots × $0.210 = $0.630 → rounds to $0.63
        assert cost == Decimal("0.63")

    def test_backend_feature_sonnet(self):
        template = get_template("backend_feature")
        cost = estimate_cost(template, "sonnet")
        # 4 slots × $0.042 = $0.168 → rounds to $0.17
        assert cost == Decimal("0.17")

    def test_full_feature_sonnet(self):
        template = get_template("full_feature")
        cost = estimate_cost(template, "sonnet")
        # 6 slots × $0.042 = $0.252 → rounds to $0.25
        assert cost == Decimal("0.25")

    def test_unknown_tier_defaults_to_sonnet(self):
        template = get_template("bug_fix")
        cost = estimate_cost(template, "imaginary_tier")
        assert cost == estimate_cost(template, "sonnet")

    def test_returns_decimal(self):
        template = get_template("bug_fix")
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
        assert "agent-tech-lead" in text
        assert "Tech Lead" in text
        assert "readiness: 90" in text
        assert "role: lead" in text

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
        # Only include tech-lead, not agent-backend → dev_impl slot has unknown agent
        agent_ids = {"agent-tech-lead"}
        errors = _validate_haiku_response(response, agent_ids)
        assert any("not in roster" in e for e in errors)

    def test_null_agent_id_is_valid(self):
        response = _valid_haiku_response()
        response["slot_assignments"]["dev_impl"]["agent_id"] = None
        agent_ids = {"agent-tech-lead"}
        errors = _validate_haiku_response(response, agent_ids)
        assert errors == []

    def test_missing_slot_assignments(self):
        response = _valid_haiku_response()
        del response["slot_assignments"]["tech_review"]
        agent_ids = {a.id for a in _make_agents()}
        errors = _validate_haiku_response(response, agent_ids)
        assert any("Missing slot" in e for e in errors)

    def test_parallel_conflict(self):
        # Use security_fix which has 2 parallel planning slots (security_plan + tech_plan)
        response = {
            "template_id": "security_fix",
            "slot_assignments": {
                "security_plan": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},
                "tech_plan": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},  # same agent → conflict
                "dev_impl": {"agent_id": "agent-backend", "agent_name": "Backend Dev"},
                "security_review": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},
                "tech_review": {"agent_id": "agent-pm-lead", "agent_name": "PM Lead"},
            },
        }
        agent_ids = {a.id for a in _make_agents()}
        errors = _validate_haiku_response(response, agent_ids)
        assert any("parallel conflict" in e for e in errors)


# ---------------------------------------------------------------------------
# DAG plan building tests
# ---------------------------------------------------------------------------


class TestBuildDagPlan:
    def test_hydrates_bug_fix(self):
        template = get_template("bug_fix")
        slot_assignments = _valid_haiku_response()["slot_assignments"]
        plan = _build_dag_plan(template, slot_assignments)

        assert "waves" in plan
        assert len(plan["waves"]) == 3

        wave1 = plan["waves"][0]
        assert wave1["wave_number"] == 1
        assert wave1["label"] == "Tech Lead diagnosing"
        assert wave1["wave_type"] == "planning"
        assert len(wave1["agents"]) == 1
        assert wave1["agents"][0]["agent_id"] == "agent-tech-lead"
        assert wave1["agents"][0]["output_key"] == "tech_plan"
        assert wave1["agents"][0]["is_lead"] is True
        # Wave 1 has no depends_on
        assert "depends_on" not in wave1["agents"][0]

        wave2 = plan["waves"][1]
        assert wave2["wave_number"] == 2
        assert wave2["wave_type"] == "execution"
        assert len(wave2["agents"]) == 1
        assert wave2["agents"][0]["agent_id"] == "agent-backend"
        assert wave2["agents"][0]["output_key"] == "dev_impl"
        assert wave2["agents"][0]["is_lead"] is False

        wave3 = plan["waves"][2]
        assert wave3["wave_type"] == "review"
        assert wave3["agents"][0]["agent_id"] == "agent-tech-lead"
        assert wave3["agents"][0]["output_key"] == "tech_review"


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
    def test_bug_fix_labels(self):
        template = get_template("bug_fix")
        labels = _build_step_labels(template)
        assert labels == [
            "Tech Lead diagnosing",
            "Developer fixing",
            "Tech Lead verifying fix",
        ]


# ---------------------------------------------------------------------------
# Fallback tests
# ---------------------------------------------------------------------------


class TestFallback:
    def test_uses_bug_fix(self):
        agents = _make_agents()
        result = _build_fallback_result(agents, "test reason")
        assert result.template_key == "bug_fix"
        assert result.is_fallback is True

    def test_picks_lead_for_lead_slots(self):
        agents = _make_agents()
        result = _build_fallback_result(agents, "test")
        # agent-tech-lead (role=lead) should fill the lead slots
        team_ids = {a["agent_id"] for a in result.assembled_team}
        assert "agent-tech-lead" in team_ids

    def test_picks_worker_for_execution_slot(self):
        agents = _make_agents()
        result = _build_fallback_result(agents, "test")
        team_ids = {a["agent_id"] for a in result.assembled_team}
        # agent-backend (role=worker) should fill the execution slot
        assert "agent-backend" in team_ids

    def test_all_slots_filled(self):
        agents = _make_agents()
        result = _build_fallback_result(agents, "test")
        template = get_template("bug_fix")
        plan_agents = [
            agent
            for wave in result.dag_plan["waves"]
            for agent in wave["agents"]
        ]
        expected_slots = sum(len(w.slots) for w in template.waves)
        assert len(plan_agents) == expected_slots

    def test_no_eligible_agents_uses_best_non_archived(self):
        agents = [
            MockAgent(id="low-1", readiness_score=30, name="Low1", role="lead"),
            MockAgent(id="low-2", readiness_score=40, name="Low2", role="worker"),
        ]
        result = _build_fallback_result(agents, "test")
        team_ids = {a["agent_id"] for a in result.assembled_team}
        # some agent is assigned
        assert len(team_ids) >= 1

    def test_includes_reason_in_reasoning(self):
        result = _build_fallback_result(_make_agents(), "Haiku exploded")
        assert "Haiku exploded" in result.reasoning


# ---------------------------------------------------------------------------
# Lead-slot enforcement tests (Ticket 13.5)
# ---------------------------------------------------------------------------


class TestEnforceLeadAssignments:
    def test_no_substitution_when_correct(self):
        """Correct assignments (lead in lead slot) should not be changed."""
        template = get_template("bug_fix")
        agents = _make_agents()
        slot_assignments = {
            "tech_plan": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},
            "dev_impl": {"agent_id": "agent-backend", "agent_name": "Backend Dev"},
            "tech_review": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},
        }
        corrected, warnings = _enforce_lead_assignments(slot_assignments, template, agents)
        assert warnings == []
        assert corrected["tech_plan"]["agent_id"] == "agent-tech-lead"
        assert corrected["dev_impl"]["agent_id"] == "agent-backend"

    def test_substitutes_worker_in_lead_slot(self):
        """Worker assigned to a lead slot must be replaced by a lead agent."""
        template = get_template("bug_fix")
        agents = _make_agents()
        # Haiku mistakenly assigns a worker to the lead planning slot
        slot_assignments = {
            "tech_plan": {"agent_id": "agent-backend", "agent_name": "Backend Dev"},
            "dev_impl": {"agent_id": "agent-backend", "agent_name": "Backend Dev"},
            "tech_review": {"agent_id": "agent-pm-lead", "agent_name": "PM Lead"},
        }
        corrected, warnings = _enforce_lead_assignments(slot_assignments, template, agents)
        assert len(warnings) == 1
        assert corrected["tech_plan"]["agent_id"] in ("agent-tech-lead", "agent-pm-lead")

    def test_no_substitution_for_null_agent(self):
        """Null agent_id slots are left as-is (orchestrator handles them)."""
        template = get_template("bug_fix")
        agents = _make_agents()
        slot_assignments = {
            "tech_plan": {"agent_id": None, "agent_name": "Generic"},
            "dev_impl": {"agent_id": "agent-backend", "agent_name": "Backend Dev"},
            "tech_review": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},
        }
        corrected, warnings = _enforce_lead_assignments(slot_assignments, template, agents)
        assert warnings == []
        assert corrected["tech_plan"]["agent_id"] is None


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

        assert result.template_key == "bug_fix"
        assert result.is_fallback is False
        assert len(result.dag_plan["waves"]) == 3
        assert len(result.assembled_team) == 2  # tech-lead + backend-dev
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
        assert result.template_key == "bug_fix"

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
        assert result.template_key == "bug_fix"

    @pytest.mark.asyncio
    async def test_unknown_agent_id_triggers_fallback(self):
        artifact = MockArtifact()
        agents = _make_agents()
        bad_response = _valid_haiku_response()
        bad_response["slot_assignments"]["dev_impl"]["agent_id"] = "nonexistent-agent"

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
        # Use a roster where the worker has low readiness
        agents = [
            MockAgent(id="agent-tech-lead", name="Tech Lead", specialization="Tech architecture", readiness_score=90, role="lead"),
            MockAgent(id="agent-dev", name="Backend Dev", specialization="Backend development", readiness_score=65, role="worker"),
        ]
        # Haiku assigns the low-readiness dev to the execution slot
        haiku_response = {
            "template_id": "bug_fix",
            "reasoning": "Bug fix needed",
            "slot_assignments": {
                "tech_plan": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},
                "dev_impl": {"agent_id": "agent-dev", "agent_name": "Backend Dev"},
                "tech_review": {"agent_id": "agent-tech-lead", "agent_name": "Tech Lead"},
            },
        }

        with patch(
            "app.agents.router._call_haiku",
            new_callable=AsyncMock,
            return_value=haiku_response,
        ):
            result = await route_brief(artifact, agents)

        assert any("Backend Dev" in w for w in result.warnings)

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
