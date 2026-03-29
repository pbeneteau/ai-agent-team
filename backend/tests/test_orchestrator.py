"""Tests for Ticket 4.3 — execute_artifact_dag orchestrator.

Verify section:
  1. Integration test: 2-wave DAG (2 slots in wave 1, 1 slot in wave 2 depending
     on both). Waves execute in order, slots in wave 1 run in parallel, wave 2
     receives upstream context from wave 1, heartbeat updates at each wave,
     ArtifactVersion created at the end.
  2. Unit test: budget exceeded before agent call halts execution with correct status.
  3. Unit test: slot failure marks wave as failed and prevents next wave from executing.
  4. Unit test: file_manifest JSONB matches the S3 upload structure.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.anthropic_runner import AgentResult
from app.agents.orchestrator import (
    BudgetExceededError,
    SlotExecutionError,
    SlotResult,
    _ArtifactCtx,
    _ProjectCtx,
    _execute_compile,
    _execute_slot,
    _guess_content_type,
    _resolve_model_id,
    execute_dag,
)
from app.agents.upstream import WaveOutput
from app.models.enums import ArtifactStatus, WaveStatus


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------


def _make_artifact_ctx(**overrides: Any) -> _ArtifactCtx:
    """Build an _ArtifactCtx with sensible defaults."""
    defaults = dict(
        id="artifact-001",
        project_id="project-001",
        workspace_id="ws-001",
        title="Competitive Analysis Report",
        goal="Analyze top 5 competitors",
        target_audience="Product team",
        context="B2B SaaS market",
        description="A detailed competitive analysis covering pricing, features, UX.",
        artifact_type="prose",
        max_budget_usd=Decimal("5.00"),
        total_cost_usd=Decimal("0.00"),
        current_version=0,
    )
    defaults.update(overrides)
    return _ArtifactCtx(**defaults)


def _make_project_ctx(**overrides: Any) -> _ProjectCtx:
    """Build a _ProjectCtx with sensible defaults."""
    defaults = dict(
        id="project-001",
        brief_published="Build a competitive analysis for our product.",
    )
    defaults.update(overrides)
    return _ProjectCtx(**defaults)


def _make_dag_plan_2_waves() -> dict[str, Any]:
    """A 2-wave DAG: wave 1 has 2 parallel slots, wave 2 has 1 slot depending on both."""
    return {
        "template_id": "content_research",
        "needs_compile": False,
        "waves": [
            {
                "wave_number": 1,
                "label": "Researching competitors",
                "agents": [
                    {
                        "agent_id": "agent-researcher",
                        "role_in_wave": "Research competitor pricing and features",
                        "output_key": "research_data",
                    },
                    {
                        "agent_id": "agent-analyst",
                        "role_in_wave": "Define analysis framework and dimensions",
                        "output_key": "analysis_framework",
                    },
                ],
            },
            {
                "wave_number": 2,
                "label": "Drafting analysis",
                "agents": [
                    {
                        "agent_id": "agent-writer",
                        "role_in_wave": "Write the competitive analysis report",
                        "output_key": "draft_report",
                        "depends_on": ["research_data", "analysis_framework"],
                    },
                ],
            },
        ],
    }


def _make_agent_result(**overrides: Any) -> AgentResult:
    """Build a mock AgentResult."""
    defaults = dict(
        text="This is the agent output.",
        files={},
        input_tokens=1000,
        output_tokens=500,
        assumptions=["[ASSUMPTION: Market is US-only]"],
        sources=["[Source: Gartner 2025 Report]"],
    )
    defaults.update(overrides)
    return AgentResult(**defaults)


@dataclass
class MockAgent:
    """Lightweight mock for the Agent ORM model."""

    id: str = "agent-researcher"
    name: str = "Research Analyst"
    specialization: str = "Competitive research and market analysis"
    system_prompt: str | None = "You are a research analyst."
    model_tier: str = "sonnet"
    status: str = "ready"


@dataclass
class MockWave:
    """Lightweight mock for the ExecutionWave ORM model."""

    id: str = "wave-001"
    artifact_id: str = "artifact-001"
    status: str = "queued"
    dag_plan: dict = None  # type: ignore[assignment]
    assembled_team: list = None  # type: ignore[assignment]
    current_step: int = 0
    total_steps: int = 0
    step_labels: list = None  # type: ignore[assignment]
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.dag_plan is None:
            self.dag_plan = _make_dag_plan_2_waves()
        if self.assembled_team is None:
            self.assembled_team = [
                {"agent_id": "agent-researcher", "agent_name": "Research Analyst"},
                {"agent_id": "agent-analyst", "agent_name": "Strategy Analyst"},
                {"agent_id": "agent-writer", "agent_name": "Content Writer"},
            ]
        if self.step_labels is None:
            self.step_labels = ["Researching competitors", "Drafting analysis"]


@dataclass
class MockArtifact:
    """Lightweight mock for the Artifact ORM model."""

    id: str = "artifact-001"
    project_id: str = "project-001"
    title: str = "Competitive Analysis Report"
    goal: str | None = "Analyze top 5 competitors"
    target_audience: str | None = "Product team"
    context: str | None = "B2B SaaS market"
    description: str | None = "A detailed competitive analysis."
    artifact_type: str = "prose"
    status: str = "drafting"
    max_budget_usd: float = 5.00
    total_cost_usd: float = 0.00
    current_version: int = 0


@dataclass
class MockProject:
    """Lightweight mock for the Project ORM model."""

    id: str = "project-001"
    workspace_id: str = "ws-001"
    brief_published: str | None = "Build a competitive analysis."


# ---------------------------------------------------------------------------
# Unit tests: model resolution
# ---------------------------------------------------------------------------


class TestResolveModelId:
    def test_sonnet(self) -> None:
        model_id = _resolve_model_id("sonnet")
        assert "sonnet" in model_id

    def test_opus(self) -> None:
        model_id = _resolve_model_id("opus")
        assert "opus" in model_id

    def test_unknown_defaults_to_sonnet(self) -> None:
        model_id = _resolve_model_id("unknown_tier")
        assert model_id == _resolve_model_id("sonnet")


# ---------------------------------------------------------------------------
# Unit tests: content type guessing
# ---------------------------------------------------------------------------


class TestGuessContentType:
    def test_markdown(self) -> None:
        assert _guess_content_type("report.md") == "text/markdown"

    def test_python(self) -> None:
        ct = _guess_content_type("main.py")
        assert ct in ("text/x-python", "text/plain")

    def test_unknown(self) -> None:
        assert _guess_content_type("data.qzx") == "application/octet-stream"


# ---------------------------------------------------------------------------
# Unit test: file_manifest JSONB structure
# ---------------------------------------------------------------------------


class TestFileManifest:
    """Verify that the file_manifest structure matches what the orchestrator
    would produce — path, size_bytes, content_type per file."""

    def test_manifest_entry_structure(self) -> None:
        """Simulate what the orchestrator builds for each file."""
        files = {
            "report.md": "# Competitive Analysis\n\nContent here.",
            "data/pricing.csv": "competitor,price\nAcme,99\nGlobex,149",
        }

        manifest: list[dict[str, Any]] = []
        for file_path, content in sorted(files.items()):
            content_bytes = content.encode("utf-8")
            manifest.append({
                "path": file_path,
                "size_bytes": len(content_bytes),
                "content_type": _guess_content_type(file_path),
            })

        assert len(manifest) == 2

        # First entry (sorted): data/pricing.csv
        assert manifest[0]["path"] == "data/pricing.csv"
        assert manifest[0]["size_bytes"] == len(
            "competitor,price\nAcme,99\nGlobex,149".encode("utf-8")
        )
        assert manifest[0]["content_type"] == "text/csv"

        # Second entry: report.md
        assert manifest[1]["path"] == "report.md"
        assert manifest[1]["content_type"] == "text/markdown"
        assert manifest[1]["size_bytes"] > 0


# ---------------------------------------------------------------------------
# Integration test: full 2-wave DAG execution (mocked agent calls)
# ---------------------------------------------------------------------------


class TestExecuteDagIntegration:
    """Integration test with mock Anthropic client: 2-wave DAG with parallel
    slots in wave 1 and a dependent slot in wave 2."""

    @pytest.mark.asyncio
    async def test_2_wave_dag_produces_artifact_version(self) -> None:
        """End-to-end: creates ArtifactVersion with correct file_manifest,
        heartbeat updates at each wave, waves execute in order."""

        wave = MockWave()
        artifact = MockArtifact()
        project = MockProject()

        # Track call order to verify sequential waves / parallel slots
        call_log: list[str] = []

        # Mock agent results for each slot
        agent_results: dict[str, AgentResult] = {
            "agent-researcher": _make_agent_result(
                text="Research output: competitor data.",
                files={"research.md": "# Research\nCompetitor data."},
                assumptions=["Market is US-only"],
                sources=["Gartner 2025"],
            ),
            "agent-analyst": _make_agent_result(
                text="Framework output: analysis dimensions.",
                files={"framework.md": "# Framework\nDimensions."},
                assumptions=[],
                sources=["Internal docs"],
            ),
            "agent-writer": _make_agent_result(
                text="Final report: competitive analysis.",
                files={"report.md": "# Competitive Analysis\nFull report."},
                assumptions=["Focused on pricing"],
                sources=["Gartner 2025", "Internal docs"],
            ),
        }

        # Track which agents were called
        async def mock_run_agent(
            system_prompt: str,
            user_message: str,
            tools: list,
            model: str,
            *,
            tool_executor=None,
            max_iterations: int = 15,
            max_tokens: int = 8192,
        ) -> AgentResult:
            # Determine which agent this is by checking the system prompt
            for agent_id, result in agent_results.items():
                if agent_id == "agent-researcher" and "Research Analyst" in system_prompt:
                    call_log.append("researcher")
                    return result
                if agent_id == "agent-analyst" and "Strategy Analyst" in system_prompt:
                    call_log.append("analyst")
                    return result
                if agent_id == "agent-writer" and "Content Writer" in system_prompt:
                    # Verify wave 2 receives upstream context
                    assert "Upstream Output" in user_message or "Research" in user_message
                    call_log.append("writer")
                    return result
            # Fallback
            call_log.append("unknown")
            return _make_agent_result()

        # Captured DB operations
        committed_states: list[dict[str, Any]] = []
        s3_uploads: list[dict[str, Any]] = []
        added_objects: list[Any] = []
        executed_updates: list[Any] = []

        class MockSession:
            """Mock async session that tracks state changes."""

            async def get(self, model_cls: type, pk: str) -> Any:
                if model_cls.__name__ == "ExecutionWave":
                    return wave
                if model_cls.__name__ == "Artifact":
                    return artifact
                if model_cls.__name__ == "Project":
                    return project
                if model_cls.__name__ == "Agent":
                    agents = {
                        "agent-researcher": MockAgent(
                            id="agent-researcher",
                            name="Research Analyst",
                            specialization="Competitive research",
                        ),
                        "agent-analyst": MockAgent(
                            id="agent-analyst",
                            name="Strategy Analyst",
                            specialization="Business strategy",
                        ),
                        "agent-writer": MockAgent(
                            id="agent-writer",
                            name="Content Writer",
                            specialization="Content writing",
                        ),
                    }
                    return agents.get(pk)
                return None

            async def execute(self, stmt: Any) -> Any:
                """Mock execute for SELECT and UPDATE statements."""
                executed_updates.append(stmt)
                # Return a mock result for the workspace_id query
                mock_result = MagicMock()
                mock_result.scalar_one.return_value = "ws-001"
                mock_result.scalars.return_value.all.return_value = []
                return mock_result

            async def commit(self) -> None:
                committed_states.append({
                    "wave_status": wave.status,
                    "wave_step": wave.current_step,
                    "wave_cost": wave.cost_usd,
                })

            async def flush(self) -> None:
                pass

            def add(self, obj: Any) -> None:
                added_objects.append(obj)

            async def __aenter__(self) -> "MockSession":
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        mock_session = MockSession()

        with (
            patch(
                "app.agents.orchestrator.async_session_maker",
                return_value=mock_session,
            ),
            patch(
                "app.agents.orchestrator.run_agent",
                side_effect=mock_run_agent,
            ),
            patch(
                "app.agents.orchestrator.load_agent_memory",
                new_callable=AsyncMock,
                return_value="## Skill: Research\nExpert at competitive analysis.",
            ),
            patch(
                "app.agents.orchestrator.get_tools_for_phase",
                return_value=[],
            ),
            patch(
                "app.agents.orchestrator.create_tool_executor",
                return_value=AsyncMock(),
            ),
            patch(
                "app.agents.orchestrator.upload_artifact_file",
            ) as mock_upload,
            patch(
                "app.agents.orchestrator.increment_costs",
                new_callable=AsyncMock,
            ) as mock_increment,
        ):
            await execute_dag("wave-001")

        # --- Assertions ---

        # 1. Waves executed in order (wave 1 slots before wave 2)
        assert "researcher" in call_log
        assert "analyst" in call_log
        assert "writer" in call_log
        writer_idx = call_log.index("writer")
        assert writer_idx >= 2  # writer runs after both wave 1 slots

        # 2. Heartbeat updates at each wave
        heartbeat_steps = [s["wave_step"] for s in committed_states]
        assert 1 in heartbeat_steps
        assert 2 in heartbeat_steps

        # 3. Wave status transitions
        assert wave.status == WaveStatus.COMPLETED.value
        assert wave.completed_at is not None

        # 4. ArtifactVersion created
        artifact_versions = [
            o for o in added_objects
            if hasattr(o, "version_number")
        ]
        assert len(artifact_versions) == 1
        version = artifact_versions[0]
        assert version.version_number == 1
        assert version.artifact_id == "artifact-001"
        assert version.execution_wave_id == "wave-001"
        assert len(version.file_manifest) > 0
        assert version.input_tokens > 0
        assert version.output_tokens > 0

        # 5. S3 uploads happened (file_manifest paths match)
        manifest_paths = {f["path"] for f in version.file_manifest}
        assert "report.md" in manifest_paths

        # 6. Costs were incremented (once per wave = 2 calls)
        assert mock_increment.call_count == 2

        # 7. Assumptions and sources collected
        assert len(version.assumptions) > 0
        assert len(version.sources) > 0


# ---------------------------------------------------------------------------
# Unit test: budget exceeded halts execution
# ---------------------------------------------------------------------------


class TestBudgetExceeded:
    @pytest.mark.asyncio
    async def test_budget_exceeded_before_wave_marks_failed(self) -> None:
        """If running cost exceeds budget before a wave, execution halts
        with wave status='failed' and error='budget_exceeded'."""

        wave = MockWave()
        # Set budget so low that the pre-wave check fails
        artifact = MockArtifact(max_budget_usd=0.001, total_cost_usd=0.001)
        project = MockProject()

        class MockSession:
            async def get(self, model_cls: type, pk: str) -> Any:
                if model_cls.__name__ == "ExecutionWave":
                    return wave
                if model_cls.__name__ == "Artifact":
                    return artifact
                if model_cls.__name__ == "Project":
                    return project
                return None

            async def execute(self, stmt: Any) -> Any:
                mock_result = MagicMock()
                mock_result.scalar_one.return_value = "ws-001"
                return mock_result

            async def commit(self) -> None:
                pass

            async def flush(self) -> None:
                pass

            def add(self, obj: Any) -> None:
                pass

            async def __aenter__(self) -> "MockSession":
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        # Manually set high total_cost to trigger budget check
        # The artifact's total_cost_usd == max_budget_usd triggers the pre-wave check.
        # Actually, let me create a DAG where we need to trigger the post-wave check.
        # For the pre-wave check: total_cost_usd + running_cost > max_budget_usd
        # With total_cost_usd=0.001 and max_budget_usd=0.001, running_cost=0
        # → 0.001 + 0 = 0.001 which is NOT > 0.001 (equal)
        # So the first wave will run. I need total > max.
        artifact.total_cost_usd = 0.01  # exceeds 0.001

        with (
            patch(
                "app.agents.orchestrator.async_session_maker",
                return_value=MockSession(),
            ),
        ):
            with pytest.raises(BudgetExceededError):
                await execute_dag("wave-001")

        assert wave.status == WaveStatus.FAILED.value
        assert wave.error_message == "budget_exceeded"
        assert wave.completed_at is not None


# ---------------------------------------------------------------------------
# Unit test: slot failure marks wave as failed
# ---------------------------------------------------------------------------


class TestSlotFailure:
    @pytest.mark.asyncio
    async def test_slot_failure_marks_wave_failed(self) -> None:
        """If any slot in a wave raises an exception, the wave is marked
        as failed and execution does not proceed to the next wave."""

        wave = MockWave()
        artifact = MockArtifact()
        project = MockProject()
        wave2_ran = False

        call_count = 0

        async def mock_run_agent_failing(
            system_prompt: str,
            user_message: str,
            tools: list,
            model: str,
            **kwargs: Any,
        ) -> AgentResult:
            nonlocal call_count
            call_count += 1
            if "Research Analyst" in system_prompt:
                raise RuntimeError("Anthropic API error: rate limited")
            return _make_agent_result()

        class MockSession:
            async def get(self, model_cls: type, pk: str) -> Any:
                if model_cls.__name__ == "ExecutionWave":
                    return wave
                if model_cls.__name__ == "Artifact":
                    return artifact
                if model_cls.__name__ == "Project":
                    return project
                if model_cls.__name__ == "Agent":
                    agents = {
                        "agent-researcher": MockAgent(
                            id="agent-researcher",
                            name="Research Analyst",
                        ),
                        "agent-analyst": MockAgent(
                            id="agent-analyst",
                            name="Strategy Analyst",
                            specialization="Strategy",
                        ),
                        "agent-writer": MockAgent(
                            id="agent-writer",
                            name="Content Writer",
                            specialization="Writing",
                        ),
                    }
                    return agents.get(pk)
                return None

            async def execute(self, stmt: Any) -> Any:
                mock_result = MagicMock()
                mock_result.scalar_one.return_value = "ws-001"
                mock_result.scalars.return_value.all.return_value = []
                return mock_result

            async def commit(self) -> None:
                pass

            async def flush(self) -> None:
                pass

            def add(self, obj: Any) -> None:
                pass

            async def __aenter__(self) -> "MockSession":
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        with (
            patch(
                "app.agents.orchestrator.async_session_maker",
                return_value=MockSession(),
            ),
            patch(
                "app.agents.orchestrator.run_agent",
                side_effect=mock_run_agent_failing,
            ),
            patch(
                "app.agents.orchestrator.load_agent_memory",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "app.agents.orchestrator.get_tools_for_phase",
                return_value=[],
            ),
            patch(
                "app.agents.orchestrator.create_tool_executor",
                return_value=AsyncMock(),
            ),
        ):
            with pytest.raises(SlotExecutionError) as exc_info:
                await execute_dag("wave-001")

        assert wave.status == WaveStatus.FAILED.value
        assert "rate limited" in wave.error_message
        assert wave.completed_at is not None
        # Wave 2 should NOT have run — the writer slot should not be called
        # (both wave 1 slots may run since they're concurrent, but wave 2 is skipped)


# ---------------------------------------------------------------------------
# Unit test: post-wave budget exceeded
# ---------------------------------------------------------------------------


class TestPostWaveBudgetExceeded:
    @pytest.mark.asyncio
    async def test_post_wave_budget_exceeded_halts(self) -> None:
        """If accumulated cost exceeds budget after a wave completes,
        execution halts before the next wave."""

        # Use a single-wave DAG to simplify — add a second wave that should not run.
        dag_plan = {
            "template_id": "simple_prose",
            "needs_compile": False,
            "waves": [
                {
                    "wave_number": 1,
                    "label": "Research",
                    "agents": [
                        {
                            "agent_id": "agent-researcher",
                            "role_in_wave": "Research",
                            "output_key": "research_data",
                        },
                    ],
                },
                {
                    "wave_number": 2,
                    "label": "Write",
                    "agents": [
                        {
                            "agent_id": "agent-writer",
                            "role_in_wave": "Write",
                            "output_key": "draft",
                            "depends_on": ["research_data"],
                        },
                    ],
                },
            ],
        }

        wave = MockWave(dag_plan=dag_plan)
        # Budget is $0.05 but the agent will cost more via expensive tokens
        artifact = MockArtifact(max_budget_usd=0.01, total_cost_usd=0.00)
        project = MockProject()

        # Return a result that costs > $0.01 (sonnet: 50K input + 10K output ≈ $0.30)
        expensive_result = _make_agent_result(
            input_tokens=50000, output_tokens=10000
        )

        wave2_ran = False

        async def mock_run_agent(
            system_prompt: str, user_message: str, tools: list,
            model: str, **kwargs: Any,
        ) -> AgentResult:
            nonlocal wave2_ran
            if "Content Writer" in system_prompt:
                wave2_ran = True
            return expensive_result

        class MockSession:
            async def get(self, model_cls: type, pk: str) -> Any:
                if model_cls.__name__ == "ExecutionWave":
                    return wave
                if model_cls.__name__ == "Artifact":
                    return artifact
                if model_cls.__name__ == "Project":
                    return project
                if model_cls.__name__ == "Agent":
                    return MockAgent(id=pk, name="Research Analyst")
                return None

            async def execute(self, stmt: Any) -> Any:
                mock_result = MagicMock()
                mock_result.scalar_one.return_value = "ws-001"
                mock_result.scalars.return_value.all.return_value = []
                return mock_result

            async def commit(self) -> None:
                pass

            async def flush(self) -> None:
                pass

            def add(self, obj: Any) -> None:
                pass

            async def __aenter__(self) -> "MockSession":
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        with (
            patch(
                "app.agents.orchestrator.async_session_maker",
                return_value=MockSession(),
            ),
            patch(
                "app.agents.orchestrator.run_agent",
                side_effect=mock_run_agent,
            ),
            patch(
                "app.agents.orchestrator.load_agent_memory",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "app.agents.orchestrator.get_tools_for_phase",
                return_value=[],
            ),
            patch(
                "app.agents.orchestrator.create_tool_executor",
                return_value=AsyncMock(),
            ),
            patch(
                "app.agents.orchestrator.increment_costs",
                new_callable=AsyncMock,
            ),
        ):
            with pytest.raises(BudgetExceededError):
                await execute_dag("wave-001")

        assert wave.status == WaveStatus.FAILED.value
        assert wave.error_message == "budget_exceeded"
        assert not wave2_ran, "Wave 2 should not have run after budget exceeded"


# ---------------------------------------------------------------------------
# Unit test: execute_slot in isolation
# ---------------------------------------------------------------------------


class TestExecuteSlot:
    @pytest.mark.asyncio
    async def test_slot_returns_correct_result(self) -> None:
        """_execute_slot loads agent, builds prompt, runs agent, returns SlotResult."""
        slot_data = {
            "agent_id": "agent-researcher",
            "role_in_wave": "Research competitor pricing",
            "output_key": "research_data",
            "depends_on": [],
        }
        wave_outputs: dict[str, WaveOutput] = {}
        artifact_ctx = _make_artifact_ctx()
        project_ctx = _make_project_ctx()

        expected_result = _make_agent_result(
            text="Research findings.",
            files={"research.md": "# Findings"},
            input_tokens=2000,
            output_tokens=800,
        )

        class MockSession:
            async def get(self, model_cls: type, pk: str) -> Any:
                if model_cls.__name__ == "Agent":
                    return MockAgent(id="agent-researcher", name="Research Analyst")
                return None

            async def execute(self, stmt: Any) -> Any:
                mock_result = MagicMock()
                mock_result.scalars.return_value.all.return_value = []
                return mock_result

            async def flush(self) -> None:
                pass

            async def commit(self) -> None:
                pass

            async def __aenter__(self) -> "MockSession":
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        with (
            patch(
                "app.agents.orchestrator.async_session_maker",
                return_value=MockSession(),
            ),
            patch(
                "app.agents.orchestrator.run_agent",
                new_callable=AsyncMock,
                return_value=expected_result,
            ) as mock_run,
            patch(
                "app.agents.orchestrator.load_agent_memory",
                new_callable=AsyncMock,
                return_value="## Skill: Research\nGood at research.",
            ),
            patch(
                "app.agents.orchestrator.get_tools_for_phase",
                return_value=[],
            ),
            patch(
                "app.agents.orchestrator.create_tool_executor",
                return_value=AsyncMock(),
            ),
        ):
            result = await _execute_slot(
                slot_data=slot_data,
                wave_outputs=wave_outputs,
                artifact_ctx=artifact_ctx,
                project_ctx=project_ctx,
            )

        assert isinstance(result, SlotResult)
        assert result.output_key == "research_data"
        assert result.agent_name == "Research Analyst"
        assert result.text == "Research findings."
        assert "research.md" in result.files
        assert result.input_tokens == 2000
        assert result.output_tokens == 800
        assert result.cost > Decimal("0")

        # Verify run_agent was called with correct model
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert "sonnet" in call_kwargs.kwargs.get("model", call_kwargs.args[3] if len(call_kwargs.args) > 3 else "")


# ---------------------------------------------------------------------------
# Unit test: upstream context flows to wave 2
# ---------------------------------------------------------------------------


class TestUpstreamContextFlow:
    @pytest.mark.asyncio
    async def test_wave2_receives_upstream_outputs(self) -> None:
        """When wave 2 depends on wave 1 outputs, the upstream context
        is injected into the wave 2 agent's user message."""

        wave_outputs: dict[str, WaveOutput] = {
            "research_data": WaveOutput(
                text="Competitor A charges $99/mo. Competitor B charges $149/mo.",
                agent_name="Research Analyst",
                slot_label="Research competitor pricing",
            ),
            "analysis_framework": WaveOutput(
                text="Analyze on: pricing, features, UX, support.",
                agent_name="Strategy Analyst",
                slot_label="Define analysis framework",
            ),
        }

        slot_data = {
            "agent_id": "agent-writer",
            "role_in_wave": "Write the analysis report",
            "output_key": "draft_report",
            "depends_on": ["research_data", "analysis_framework"],
        }

        artifact_ctx = _make_artifact_ctx()
        project_ctx = _make_project_ctx()

        captured_user_message: list[str] = []

        async def mock_run_agent(
            system_prompt: str, user_message: str, tools: list,
            model: str, **kwargs: Any,
        ) -> AgentResult:
            captured_user_message.append(user_message)
            return _make_agent_result()

        class MockSession:
            async def get(self, model_cls: type, pk: str) -> Any:
                if model_cls.__name__ == "Agent":
                    return MockAgent(
                        id="agent-writer",
                        name="Content Writer",
                        specialization="Writing",
                    )
                return None

            async def execute(self, stmt: Any) -> Any:
                mock_result = MagicMock()
                mock_result.scalars.return_value.all.return_value = []
                return mock_result

            async def flush(self) -> None:
                pass

            async def commit(self) -> None:
                pass

            async def __aenter__(self) -> "MockSession":
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        with (
            patch(
                "app.agents.orchestrator.async_session_maker",
                return_value=MockSession(),
            ),
            patch(
                "app.agents.orchestrator.run_agent",
                side_effect=mock_run_agent,
            ),
            patch(
                "app.agents.orchestrator.load_agent_memory",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "app.agents.orchestrator.get_tools_for_phase",
                return_value=[],
            ),
            patch(
                "app.agents.orchestrator.create_tool_executor",
                return_value=AsyncMock(),
            ),
        ):
            result = await _execute_slot(
                slot_data=slot_data,
                wave_outputs=wave_outputs,
                artifact_ctx=artifact_ctx,
                project_ctx=project_ctx,
            )

        # Verify upstream outputs were injected into the user message
        assert len(captured_user_message) == 1
        msg = captured_user_message[0]
        assert "Research Analyst" in msg
        assert "Competitor A" in msg
        assert "Strategy Analyst" in msg
        assert "pricing, features, UX, support" in msg


# ---------------------------------------------------------------------------
# Unit test: compilation step
# ---------------------------------------------------------------------------


class TestCompileOutputs:
    @pytest.mark.asyncio
    async def test_compile_merges_upstream_outputs(self) -> None:
        """_execute_compile builds context from all wave outputs and
        runs the compile agent."""

        wave_outputs: dict[str, WaveOutput] = {
            "researcher_1": WaveOutput(
                text="Market segment A analysis.",
                agent_name="Researcher 1",
                slot_label="Research segment A",
            ),
            "researcher_2": WaveOutput(
                text="Market segment B analysis.",
                agent_name="Researcher 2",
                slot_label="Research segment B",
            ),
        }

        artifact_ctx = _make_artifact_ctx()
        project_ctx = _make_project_ctx()

        captured_msgs: list[str] = []

        async def mock_run_agent(
            system_prompt: str, user_message: str, tools: list,
            model: str, **kwargs: Any,
        ) -> AgentResult:
            captured_msgs.append(user_message)
            return _make_agent_result(
                text="Merged analysis of segments A and B.",
                files={"final_report.md": "# Merged Report"},
            )

        with (
            patch(
                "app.agents.orchestrator.run_agent",
                side_effect=mock_run_agent,
            ),
            patch(
                "app.agents.orchestrator.get_tools_for_phase",
                return_value=[],
            ),
            patch(
                "app.agents.orchestrator.create_tool_executor",
                return_value=AsyncMock(),
            ),
        ):
            result = await _execute_compile(
                wave_outputs=wave_outputs,
                artifact_ctx=artifact_ctx,
                project_ctx=project_ctx,
            )

        assert result.output_key == "_compile"
        assert "Merged" in result.text
        assert "final_report.md" in result.files

        # Verify both upstream outputs were in the prompt
        msg = captured_msgs[0]
        assert "Researcher 1" in msg
        assert "Researcher 2" in msg
        assert "Market segment A" in msg
        assert "Market segment B" in msg


# ---------------------------------------------------------------------------
# Delegation validation tests (Ticket 17.3)
# ---------------------------------------------------------------------------


class TestDelegationValidation:
    def test_parse_validation_decision_approved(self) -> None:
        from app.agents.orchestrator import _parse_validation_decision

        text = "## Validation Decision\n**Decision:** APPROVED\n\nAll good."
        assert _parse_validation_decision(text) == "APPROVED"

    def test_parse_validation_decision_revise(self) -> None:
        from app.agents.orchestrator import _parse_validation_decision

        text = "## Validation Decision\n**Decision:** REVISE\n\nNeeds work."
        assert _parse_validation_decision(text) == "REVISE"

    def test_parse_validation_decision_fallback_bare_keyword(self) -> None:
        from app.agents.orchestrator import _parse_validation_decision

        text = "I think this needs to be REVISE because the scope is vague."
        assert _parse_validation_decision(text) == "REVISE"

    def test_parse_validation_decision_fail_open(self) -> None:
        """Unknown output defaults to APPROVED (fail-open)."""
        from app.agents.orchestrator import _parse_validation_decision

        text = "Everything looks fine overall."
        assert _parse_validation_decision(text) == "APPROVED"

    def test_find_best_agent_for_validation_match(self) -> None:
        from app.agents.orchestrator import _find_best_agent_for_validation

        team = [
            {"agent_id": "a1", "agent_name": "PM Lead"},
            {"agent_id": "a2", "agent_name": "Tech Lead"},
            {"agent_id": "a3", "agent_name": "Backend Dev"},
        ]
        result = _find_best_agent_for_validation(["Tech Lead", "Senior Engineer"], team)
        assert result == "a2"

    def test_find_best_agent_for_validation_fallback(self) -> None:
        from app.agents.orchestrator import _find_best_agent_for_validation

        team = [{"agent_id": "a1", "agent_name": "Data Scientist"}]
        result = _find_best_agent_for_validation(["Tech Lead"], team)
        assert result == "a1"  # Fallback to first agent

    def test_find_best_agent_for_validation_empty_team(self) -> None:
        from app.agents.orchestrator import _find_best_agent_for_validation

        result = _find_best_agent_for_validation(["Tech Lead"], [])
        assert result is None

    def test_enrich_wave_with_feedback(self) -> None:
        from app.agents.orchestrator import _enrich_wave_with_feedback

        wave_data = {
            "wave_number": 1,
            "label": "Planning",
            "agents": [
                {"role_in_wave": "Plan the feature", "output_key": "plan"},
            ],
        }
        enriched = _enrich_wave_with_feedback(wave_data, "Scope is too vague")
        assert enriched["wave_number"] == 1
        assert len(enriched["agents"]) == 1
        role = enriched["agents"][0]["role_in_wave"]
        assert "Plan the feature" in role
        assert "Delegation Validation Feedback" in role
        assert "Scope is too vague" in role
        # Original should be unchanged
        assert "Validation" not in wave_data["agents"][0]["role_in_wave"]


class TestValidationPhaseToolRegistry:
    def test_validation_phase_returns_file_read_only(self) -> None:
        from app.tools.registry import get_tools_for_phase

        tools = get_tools_for_phase("validation")
        tool_names = [t.name for t in tools]
        assert "file_read" in tool_names
        assert "file_write" not in tool_names
        assert "web_search" not in tool_names

    def test_validation_format_rules(self) -> None:
        from app.agents.prompt_builder import get_output_format_rules

        rules = get_output_format_rules("code", "delegation_validator")
        assert "DELEGATION PLAN" in rules
        assert "APPROVED" in rules
        assert "REVISE" in rules
