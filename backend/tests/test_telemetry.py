"""Tests for Ticket 16.1 — execution telemetry.

Covers:
  1. Metric dataclass construction and serialization.
  2. Emit functions produce structured JSON log lines.
  3. Timer context manager measures elapsed time.
  4. AgentResult new telemetry fields populated by run_agent().
  5. Orchestrator emits ExecutionMetrics after slot execution.
  6. Review loop emits ReviewLoopMetrics after consensus.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.anthropic_runner import AgentResult, run_agent
from app.agents.telemetry import (
    CompactionMetrics,
    ExecutionMetrics,
    ReviewLoopMetrics,
    Timer,
    emit_compaction_metrics,
    emit_execution_metrics,
    emit_review_loop_metrics,
)


# ---------------------------------------------------------------------------
# Helpers — reused from test_anthropic_runner
# ---------------------------------------------------------------------------


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class FakeToolUseBlock:
    type: str = "tool_use"
    name: str = ""
    input: dict[str, Any] = None  # type: ignore[assignment]
    id: str = "tool_call_1"

    def __post_init__(self) -> None:
        if self.input is None:
            self.input = {}


@dataclass
class FakeResponse:
    content: list[Any]
    stop_reason: str
    usage: FakeUsage


@dataclass
class FakeTool:
    name: str

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": f"Test tool: {self.name}",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }


# ---------------------------------------------------------------------------
# Unit tests: metric dataclasses
# ---------------------------------------------------------------------------


class TestExecutionMetrics:
    def test_construction_with_defaults(self) -> None:
        m = ExecutionMetrics(
            wave_id="wave-1",
            slot_key="backend_dev",
            agent_id="agent-1",
            phase="execution",
            model="claude-sonnet-4-20250514",
            tool_loop_iterations=3,
        )
        assert m.wave_id == "wave-1"
        assert m.tool_calls == []
        assert m.input_tokens == 0
        assert m.context_tokens_peak == 0
        assert m.review_decision is None
        assert m.compaction_triggered is False

    def test_construction_with_all_fields(self) -> None:
        m = ExecutionMetrics(
            wave_id="wave-2",
            slot_key="reviewer",
            agent_id="agent-2",
            phase="review",
            model="claude-sonnet-4-20250514",
            tool_loop_iterations=1,
            tool_calls=["file_read", "file_read"],
            input_tokens=5000,
            output_tokens=2000,
            elapsed_seconds=12.5,
            context_tokens_peak=4800,
            review_decision="APPROVE",
            compaction_triggered=True,
        )
        assert m.tool_calls == ["file_read", "file_read"]
        assert m.review_decision == "APPROVE"


class TestReviewLoopMetrics:
    def test_construction(self) -> None:
        m = ReviewLoopMetrics(
            wave_id="wave-1",
            iteration_number=2,
            consensus_decision="REVISE",
            decisions_by_lead={"Tech Lead": "APPROVE", "PM Lead": "REVISE"},
            elapsed_seconds=45.2,
        )
        assert m.consensus_decision == "REVISE"
        assert len(m.decisions_by_lead) == 2

    def test_defaults(self) -> None:
        m = ReviewLoopMetrics(
            wave_id="w",
            iteration_number=1,
            consensus_decision="APPROVE",
        )
        assert m.decisions_by_lead == {}
        assert m.elapsed_seconds == 0.0


class TestCompactionMetrics:
    def test_construction(self) -> None:
        m = CompactionMetrics(
            agent_id="agent-1",
            before_tokens=9000,
            after_tokens=5500,
            entries_before=12,
            entries_after=3,
            elapsed_seconds=2.1,
        )
        assert m.before_tokens == 9000
        assert m.after_tokens == 5500


# ---------------------------------------------------------------------------
# Unit tests: emit functions produce valid JSON logs
# ---------------------------------------------------------------------------


class TestEmitFunctions:
    def test_emit_execution_metrics(self, caplog: pytest.LogCaptureFixture) -> None:
        m = ExecutionMetrics(
            wave_id="wave-1",
            slot_key="backend_dev",
            agent_id="agent-1",
            phase="execution",
            model="claude-sonnet-4-20250514",
            tool_loop_iterations=5,
            tool_calls=["file_write", "file_read"],
            input_tokens=3000,
            output_tokens=1500,
            elapsed_seconds=8.2,
            context_tokens_peak=2800,
        )

        with caplog.at_level(logging.INFO, logger="telemetry"):
            emit_execution_metrics(m)

        assert len(caplog.records) == 1
        payload = json.loads(caplog.records[0].message)
        assert payload["event"] == "agent_run"
        assert payload["wave_id"] == "wave-1"
        assert payload["slot_key"] == "backend_dev"
        assert payload["tool_loop_iterations"] == 5
        assert payload["tool_calls"] == ["file_write", "file_read"]
        assert payload["context_tokens_peak"] == 2800

    def test_emit_review_loop_metrics(self, caplog: pytest.LogCaptureFixture) -> None:
        m = ReviewLoopMetrics(
            wave_id="wave-1",
            iteration_number=1,
            consensus_decision="MINOR_FIX",
            decisions_by_lead={"Tech Lead": "MINOR_FIX", "PM Lead": "APPROVE"},
            elapsed_seconds=30.0,
        )

        with caplog.at_level(logging.INFO, logger="telemetry"):
            emit_review_loop_metrics(m)

        assert len(caplog.records) == 1
        payload = json.loads(caplog.records[0].message)
        assert payload["event"] == "review_loop"
        assert payload["consensus_decision"] == "MINOR_FIX"
        assert payload["decisions_by_lead"]["Tech Lead"] == "MINOR_FIX"

    def test_emit_compaction_metrics(self, caplog: pytest.LogCaptureFixture) -> None:
        m = CompactionMetrics(
            agent_id="agent-1",
            before_tokens=9500,
            after_tokens=5200,
            entries_before=15,
            entries_after=4,
            elapsed_seconds=3.5,
        )

        with caplog.at_level(logging.INFO, logger="telemetry"):
            emit_compaction_metrics(m)

        assert len(caplog.records) == 1
        payload = json.loads(caplog.records[0].message)
        assert payload["event"] == "memory_compaction"
        assert payload["before_tokens"] == 9500
        assert payload["after_tokens"] == 5200
        assert payload["entries_before"] == 15
        assert payload["entries_after"] == 4


# ---------------------------------------------------------------------------
# Unit tests: Timer
# ---------------------------------------------------------------------------


class TestTimer:
    def test_measures_elapsed(self) -> None:
        timer = Timer()
        with timer:
            pass  # near-zero time
        assert timer.elapsed >= 0.0
        assert isinstance(timer.elapsed, float)

    def test_initial_state(self) -> None:
        timer = Timer()
        assert timer.elapsed == 0.0


# ---------------------------------------------------------------------------
# Integration test: run_agent populates telemetry fields
# ---------------------------------------------------------------------------


class TestRunAgentTelemetryFields:
    @pytest.mark.asyncio
    async def test_end_turn_no_tools_populates_telemetry(self) -> None:
        """Simple end_turn with no tools → 1 iteration, empty tool log."""
        response = FakeResponse(
            content=[FakeTextBlock(text="Done.")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=200, output_tokens=50),
        )
        mock_create = AsyncMock(return_value=response)

        with patch("app.agents.anthropic_runner.get_anthropic_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_gc.return_value = mock_client

            result = await run_agent(
                system_prompt="test",
                user_message="test",
                tools=[],
                model="claude-sonnet-4-20250514",
            )

        assert result.tool_loop_iterations == 1
        assert result.tool_calls_log == []
        assert result.context_tokens_peak == 200

    @pytest.mark.asyncio
    async def test_tool_calls_tracked(self) -> None:
        """Tool calls are logged in order across iterations."""
        tool_response = FakeResponse(
            content=[
                FakeToolUseBlock(name="file_read", input={"path": "a.py"}, id="t1"),
                FakeToolUseBlock(name="file_write", input={"path": "b.py", "content": "x"}, id="t2"),
            ],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=300, output_tokens=100),
        )
        end_response = FakeResponse(
            content=[FakeTextBlock(text="Done.")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=500, output_tokens=80),
        )
        mock_create = AsyncMock(side_effect=[tool_response, end_response])

        async def tool_executor(name: str, inp: dict[str, Any]) -> str:
            return "ok"

        tools = [FakeTool(name="file_read"), FakeTool(name="file_write")]

        with patch("app.agents.anthropic_runner.get_anthropic_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_gc.return_value = mock_client

            result = await run_agent(
                system_prompt="test",
                user_message="test",
                tools=tools,
                model="claude-sonnet-4-20250514",
                tool_executor=tool_executor,
            )

        assert result.tool_loop_iterations == 2
        assert result.tool_calls_log == ["file_read", "file_write"]

    @pytest.mark.asyncio
    async def test_context_tokens_peak_tracks_max(self) -> None:
        """Peak context is the max input_tokens across all API calls."""
        # First call: small context. Second call: larger context. Third: end.
        responses = [
            FakeResponse(
                content=[FakeToolUseBlock(name="web_search", input={"q": "x"}, id="t1")],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=1000, output_tokens=50),
            ),
            FakeResponse(
                content=[FakeToolUseBlock(name="web_search", input={"q": "y"}, id="t2")],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=3000, output_tokens=60),
            ),
            FakeResponse(
                content=[FakeTextBlock(text="Done.")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=2500, output_tokens=100),
            ),
        ]
        mock_create = AsyncMock(side_effect=responses)

        async def tool_executor(name: str, inp: dict[str, Any]) -> str:
            return "result"

        tools = [FakeTool(name="web_search")]

        with patch("app.agents.anthropic_runner.get_anthropic_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_gc.return_value = mock_client

            result = await run_agent(
                system_prompt="test",
                user_message="test",
                tools=tools,
                model="claude-sonnet-4-20250514",
                tool_executor=tool_executor,
            )

        # Peak should be 3000 (the second call's input)
        assert result.context_tokens_peak == 3000
        assert result.tool_loop_iterations == 3
        assert result.tool_calls_log == ["web_search", "web_search"]

    @pytest.mark.asyncio
    async def test_unexpected_stop_reason_populates_telemetry(self) -> None:
        """Unexpected stop_reason still returns telemetry fields."""
        response = FakeResponse(
            content=[FakeTextBlock(text="Partial.")],
            stop_reason="max_tokens",
            usage=FakeUsage(input_tokens=400, output_tokens=200),
        )
        mock_create = AsyncMock(return_value=response)

        with patch("app.agents.anthropic_runner.get_anthropic_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_gc.return_value = mock_client

            result = await run_agent(
                system_prompt="test",
                user_message="test",
                tools=[],
                model="claude-sonnet-4-20250514",
            )

        assert result.tool_loop_iterations == 1
        assert result.context_tokens_peak == 400


# ---------------------------------------------------------------------------
# Integration test: orchestrator slot emits telemetry
# ---------------------------------------------------------------------------


class TestOrchestratorTelemetryEmission:
    @pytest.mark.asyncio
    async def test_execute_slot_emits_metrics(self) -> None:
        """_execute_slot calls emit_execution_metrics after run_agent."""
        from app.agents.orchestrator import _execute_slot, _ArtifactCtx, _ProjectCtx
        from app.agents.upstream import WaveOutput
        from decimal import Decimal

        slot_data = {
            "agent_id": "agent-1",
            "role_in_wave": "Implement feature",
            "output_key": "impl",
            "depends_on": [],
        }
        artifact_ctx = _ArtifactCtx(
            id="art-1", project_id="proj-1", workspace_id="ws-1",
            title="Test", goal=None, target_audience=None, context=None,
            description=None, artifact_type="code",
            max_budget_usd=Decimal("10"), total_cost_usd=Decimal("0"),
            current_version=0,
        )
        project_ctx = _ProjectCtx(id="proj-1", brief_published="Build it.")

        mock_result = AgentResult(
            text="Done.",
            files={"main.py": "print('hi')"},
            input_tokens=1000,
            output_tokens=500,
            tool_loop_iterations=2,
            tool_calls_log=["file_write"],
            context_tokens_peak=950,
        )

        @dataclass
        class MockAgent:
            id: str = "agent-1"
            name: str = "Dev Agent"
            specialization: str = "Backend"
            system_prompt: str | None = None
            model_tier: str = "sonnet"
            status: str = "ready"

        class MockSession:
            async def get(self, model_cls: type, pk: str) -> Any:
                if model_cls.__name__ == "Agent":
                    return MockAgent()
                return None

            async def execute(self, stmt: Any) -> Any:
                mock_r = MagicMock()
                mock_r.scalars.return_value.all.return_value = []
                return mock_r

            async def flush(self) -> None:
                pass

            async def commit(self) -> None:
                pass

            async def __aenter__(self) -> "MockSession":
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        emitted: list[ExecutionMetrics] = []

        def capture_emit(metrics: ExecutionMetrics) -> None:
            emitted.append(metrics)

        with (
            patch("app.agents.orchestrator.async_session_maker", return_value=MockSession()),
            patch("app.agents.orchestrator.run_agent", new_callable=AsyncMock, return_value=mock_result),
            patch("app.agents.orchestrator.load_agent_memory", new_callable=AsyncMock, return_value=""),
            patch("app.agents.orchestrator.get_tools_for_phase", return_value=[]),
            patch("app.agents.orchestrator.create_tool_executor", return_value=AsyncMock()),
            patch("app.agents.orchestrator.emit_execution_metrics", side_effect=capture_emit),
        ):
            result = await _execute_slot(
                slot_data=slot_data,
                wave_outputs={},
                artifact_ctx=artifact_ctx,
                project_ctx=project_ctx,
            )

        assert len(emitted) == 1
        m = emitted[0]
        assert m.slot_key == "impl"
        assert m.agent_id == "agent-1"
        assert m.phase == "execution"
        assert m.tool_loop_iterations == 2
        assert m.tool_calls == ["file_write"]
        assert m.input_tokens == 1000
        assert m.output_tokens == 500
        assert m.context_tokens_peak == 950
        assert m.elapsed_seconds >= 0.0


# ---------------------------------------------------------------------------
# Unit tests: AgentResult backward compatibility
# ---------------------------------------------------------------------------


class TestAgentResultBackwardCompat:
    """Ensure new telemetry fields have safe defaults so existing code
    that constructs AgentResult without them still works."""

    def test_defaults(self) -> None:
        r = AgentResult(text="hello")
        assert r.tool_loop_iterations == 0
        assert r.tool_calls_log == []
        assert r.context_tokens_peak == 0

    def test_immutable(self) -> None:
        r = AgentResult(text="hello", tool_loop_iterations=5)
        with pytest.raises(AttributeError):
            r.tool_loop_iterations = 10  # type: ignore[misc]
