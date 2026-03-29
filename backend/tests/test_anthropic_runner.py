"""Tests for app.agents.anthropic_runner — agent execution loop.

Covers:
- Integration test: mock Anthropic client → tool call → end_turn → AgentResult
- Unit tests: assumption extraction regex
- Unit tests: source extraction regex
- Unit test: AgentMaxIterationError raised on iteration exhaustion
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.anthropic_runner import (
    ASSUMPTION_PATTERN,
    SOURCE_PATTERN,
    TBD_PATTERN,
    AgentMaxIterationError,
    AgentResult,
    extract_assumptions,
    extract_sources,
    run_agent,
)


# ---------------------------------------------------------------------------
# Helpers — lightweight fakes for Anthropic response objects
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
    """Minimal ToolSpec implementation for tests."""

    name: str

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": f"Test tool: {self.name}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": [],
            },
        }


# ---------------------------------------------------------------------------
# Unit tests: assumption extraction (TDD-03 Section 7.3)
# ---------------------------------------------------------------------------


class TestExtractAssumptions:
    def test_basic_assumption(self) -> None:
        text = "Some text [ASSUMPTION: US market only] more text."
        result = extract_assumptions(text)
        assert result == ["US market only"]

    def test_multiple_assumptions(self) -> None:
        text = (
            "[ASSUMPTION: US market only] and also "
            "[ASSUMPTION: English language assumed]"
        )
        result = extract_assumptions(text)
        assert result == ["US market only", "English language assumed"]

    def test_case_insensitive(self) -> None:
        text = "[assumption: lowercase works] and [Assumption: Mixed case too]"
        result = extract_assumptions(text)
        assert result == ["lowercase works", "Mixed case too"]

    def test_tbd_entries(self) -> None:
        text = "[TBD: Need pricing details from client]"
        result = extract_assumptions(text)
        assert result == ["TBD — Need pricing details from client"]

    def test_mixed_assumptions_and_tbd(self) -> None:
        text = (
            "[ASSUMPTION: Using React 18] "
            "[TBD: deployment target unclear]"
        )
        result = extract_assumptions(text)
        assert len(result) == 2
        assert result[0] == "Using React 18"
        assert result[1] == "TBD — deployment target unclear"

    def test_no_assumptions(self) -> None:
        text = "Clean text with no annotations."
        result = extract_assumptions(text)
        assert result == []

    def test_assumption_with_extra_whitespace(self) -> None:
        text = "[ASSUMPTION:   padded text   ]"
        result = extract_assumptions(text)
        assert result == ["padded text"]

    def test_assumption_in_code_comment(self) -> None:
        """Assumptions can appear in code comments (TDD-03 Section 4.4)."""
        text = "// [ASSUMPTION: API returns JSON]"
        result = extract_assumptions(text)
        assert result == ["API returns JSON"]

    def test_assumption_pattern_compiled(self) -> None:
        """Regex is compiled at module level, not per-call."""
        assert ASSUMPTION_PATTERN.pattern == r"\[ASSUMPTION:\s*(.+?)\]"

    def test_tbd_pattern_compiled(self) -> None:
        assert TBD_PATTERN.pattern == r"\[TBD:\s*(.+?)\]"


# ---------------------------------------------------------------------------
# Unit tests: source extraction
# ---------------------------------------------------------------------------


class TestExtractSources:
    def test_basic_source(self) -> None:
        text = "[Source: https://example.com]"
        result = extract_sources(text)
        assert result == ["https://example.com"]

    def test_multiple_sources(self) -> None:
        text = (
            "[Source: https://a.com] and [Source: https://b.com/page]"
        )
        result = extract_sources(text)
        assert result == ["https://a.com", "https://b.com/page"]

    def test_source_with_text_reference(self) -> None:
        text = "[Source: Anthropic documentation, tool use guide]"
        result = extract_sources(text)
        assert result == ["Anthropic documentation, tool use guide"]

    def test_case_insensitive(self) -> None:
        text = "[source: https://lower.com]"
        result = extract_sources(text)
        assert result == ["https://lower.com"]

    def test_no_sources(self) -> None:
        text = "No sources here."
        result = extract_sources(text)
        assert result == []

    def test_source_pattern_compiled(self) -> None:
        assert SOURCE_PATTERN.pattern == r"\[Source:\s*(.+?)\]"


# ---------------------------------------------------------------------------
# Unit tests: AgentMaxIterationError
# ---------------------------------------------------------------------------


class TestAgentMaxIterationError:
    def test_fields(self) -> None:
        err = AgentMaxIterationError(
            "Agent did not complete in 15 iterations",
            iterations=15,
            input_tokens=50000,
            output_tokens=12000,
        )
        assert str(err) == "Agent did not complete in 15 iterations"
        assert err.iterations == 15
        assert err.input_tokens == 50000
        assert err.output_tokens == 12000

    def test_is_exception(self) -> None:
        err = AgentMaxIterationError(
            "test", iterations=1, input_tokens=0, output_tokens=0
        )
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# Unit tests: AgentResult dataclass
# ---------------------------------------------------------------------------


class TestAgentResult:
    def test_defaults(self) -> None:
        r = AgentResult(text="hello")
        assert r.text == "hello"
        assert r.files == {}
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.assumptions == []
        assert r.sources == []

    def test_immutable(self) -> None:
        r = AgentResult(text="hello")
        with pytest.raises(AttributeError):
            r.text = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration test: full loop with mock Anthropic client
# ---------------------------------------------------------------------------


class TestRunAgentIntegration:
    """Test the full run_agent loop using a mocked Anthropic client.

    Scenario: model makes one tool call (file_write), then returns end_turn
    with final text containing an assumption and a source.
    """

    @pytest.mark.asyncio
    async def test_tool_call_then_end_turn(self) -> None:
        """Agent calls file_write once, then produces final text."""
        # Response 1: tool_use — model asks to write a file
        tool_use_response = FakeResponse(
            content=[
                FakeTextBlock(text="Let me write the file."),
                FakeToolUseBlock(
                    name="file_write",
                    input={"path": "src/index.ts", "content": "console.log('hello');"},
                    id="tool_1",
                ),
            ],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=100, output_tokens=50),
        )

        # Response 2: end_turn — model produces final output
        end_turn_response = FakeResponse(
            content=[
                FakeTextBlock(
                    text=(
                        "# Output\n\n"
                        "Here is the file. "
                        "[ASSUMPTION: Using TypeScript strict mode] "
                        "[Source: https://ts.dev/docs]"
                    ),
                ),
            ],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=200, output_tokens=100),
        )

        mock_create = AsyncMock(side_effect=[tool_use_response, end_turn_response])

        # Tool executor that returns a success message
        async def tool_executor(name: str, inp: dict[str, Any]) -> str:
            if name == "file_write":
                return f"File written: {inp.get('path')}"
            return "ok"

        tools = [FakeTool(name="file_write")]

        with patch(
            "app.agents.anthropic_runner.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_get_client.return_value = mock_client

            result = await run_agent(
                system_prompt="You are a coder.",
                user_message="Write a hello world file.",
                tools=tools,
                model="claude-sonnet-4-20250514",
                tool_executor=tool_executor,
                max_iterations=15,
            )

        # Verify AgentResult
        assert isinstance(result, AgentResult)
        assert "Output" in result.text
        assert result.files == {"src/index.ts": "console.log('hello');"}
        assert result.input_tokens == 300  # 100 + 200
        assert result.output_tokens == 150  # 50 + 100
        assert result.assumptions == ["Using TypeScript strict mode"]
        assert result.sources == ["https://ts.dev/docs"]

        # Verify the API was called exactly twice
        assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_max_iterations_exceeded(self) -> None:
        """Agent loops forever with tool_use → raises AgentMaxIterationError."""
        # Every response is a tool_use — the model never signals end_turn
        infinite_tool_response = FakeResponse(
            content=[
                FakeToolUseBlock(
                    name="web_search",
                    input={"query": "something"},
                    id="tool_loop",
                ),
            ],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=50, output_tokens=30),
        )

        mock_create = AsyncMock(return_value=infinite_tool_response)

        async def tool_executor(name: str, inp: dict[str, Any]) -> str:
            return "some result"

        tools = [FakeTool(name="web_search")]

        with patch(
            "app.agents.anthropic_runner.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_get_client.return_value = mock_client

            with pytest.raises(AgentMaxIterationError) as exc_info:
                await run_agent(
                    system_prompt="You are a researcher.",
                    user_message="Find info.",
                    tools=tools,
                    model="claude-sonnet-4-20250514",
                    tool_executor=tool_executor,
                    max_iterations=3,
                )

            err = exc_info.value
            assert err.iterations == 3
            assert err.input_tokens == 150   # 50 * 3
            assert err.output_tokens == 90   # 30 * 3

    @pytest.mark.asyncio
    async def test_no_tools_end_turn(self) -> None:
        """Agent with no tools returns immediately on end_turn."""
        response = FakeResponse(
            content=[
                FakeTextBlock(text="The brief is sufficient."),
            ],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=80, output_tokens=20),
        )

        mock_create = AsyncMock(return_value=response)

        with patch(
            "app.agents.anthropic_runner.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_get_client.return_value = mock_client

            result = await run_agent(
                system_prompt="You are a reviewer.",
                user_message="Check this brief.",
                tools=[],
                model="claude-haiku-4-5-20251001",
                max_iterations=15,
            )

        assert result.text == "The brief is sufficient."
        assert result.files == {}
        assert result.input_tokens == 80
        assert result.output_tokens == 20
        assert mock_create.call_count == 1

    @pytest.mark.asyncio
    async def test_tool_executor_error_is_captured(self) -> None:
        """If a tool executor raises, the error is sent back as a tool result."""
        tool_use_response = FakeResponse(
            content=[
                FakeToolUseBlock(
                    name="web_search",
                    input={"query": "test"},
                    id="tool_err",
                ),
            ],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=50, output_tokens=20),
        )

        end_response = FakeResponse(
            content=[FakeTextBlock(text="Done despite error.")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=60, output_tokens=30),
        )

        mock_create = AsyncMock(side_effect=[tool_use_response, end_response])

        async def failing_executor(name: str, inp: dict[str, Any]) -> str:
            raise RuntimeError("Network timeout")

        tools = [FakeTool(name="web_search")]

        with patch(
            "app.agents.anthropic_runner.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_get_client.return_value = mock_client

            result = await run_agent(
                system_prompt="You are a researcher.",
                user_message="Search.",
                tools=tools,
                model="claude-sonnet-4-20250514",
                tool_executor=failing_executor,
                max_iterations=15,
            )

        assert result.text == "Done despite error."

    @pytest.mark.asyncio
    async def test_no_executor_with_tool_use_raises(self) -> None:
        """If model returns tool_use but no executor provided, raise RuntimeError."""
        tool_use_response = FakeResponse(
            content=[
                FakeToolUseBlock(
                    name="file_write",
                    input={"path": "x.txt", "content": "hi"},
                    id="tool_no_exec",
                ),
            ],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=50, output_tokens=20),
        )

        mock_create = AsyncMock(return_value=tool_use_response)

        tools = [FakeTool(name="file_write")]

        with patch(
            "app.agents.anthropic_runner.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_get_client.return_value = mock_client

            with pytest.raises(RuntimeError, match="no tool_executor"):
                await run_agent(
                    system_prompt="test",
                    user_message="test",
                    tools=tools,
                    model="claude-sonnet-4-20250514",
                    tool_executor=None,
                    max_iterations=15,
                )

    @pytest.mark.asyncio
    async def test_multiple_file_writes_collected(self) -> None:
        """Multiple file_write calls accumulate in result.files."""
        # Response 1: two file_write tool calls
        tool_response = FakeResponse(
            content=[
                FakeToolUseBlock(
                    name="file_write",
                    input={"path": "a.txt", "content": "aaa"},
                    id="fw1",
                ),
                FakeToolUseBlock(
                    name="file_write",
                    input={"path": "b.txt", "content": "bbb"},
                    id="fw2",
                ),
            ],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=100, output_tokens=60),
        )

        end_response = FakeResponse(
            content=[FakeTextBlock(text="Files written.")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=120, output_tokens=40),
        )

        mock_create = AsyncMock(side_effect=[tool_response, end_response])

        async def tool_executor(name: str, inp: dict[str, Any]) -> str:
            return f"Written: {inp.get('path')}"

        tools = [FakeTool(name="file_write")]

        with patch(
            "app.agents.anthropic_runner.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_get_client.return_value = mock_client

            result = await run_agent(
                system_prompt="coder",
                user_message="write files",
                tools=tools,
                model="claude-sonnet-4-20250514",
                tool_executor=tool_executor,
                max_iterations=15,
            )

        assert result.files == {"a.txt": "aaa", "b.txt": "bbb"}


# ---------------------------------------------------------------------------
# Unit tests: context summarization helpers (Ticket 17.4)
# ---------------------------------------------------------------------------


class TestEstimateMessagesTokens:
    def test_simple_string_content(self) -> None:
        from app.agents.anthropic_runner import _estimate_messages_tokens

        messages = [{"role": "user", "content": "Hello world"}]
        tokens = _estimate_messages_tokens(messages)
        assert tokens > 0
        assert tokens < 10  # "Hello world" is ~2 tokens

    def test_multiple_messages(self) -> None:
        from app.agents.anthropic_runner import _estimate_messages_tokens

        messages = [
            {"role": "user", "content": "First message with some content."},
            {"role": "assistant", "content": "Response with more content."},
            {"role": "user", "content": "Follow up."},
        ]
        tokens = _estimate_messages_tokens(messages)
        assert tokens > 10

    def test_tool_result_content(self) -> None:
        from app.agents.anthropic_runner import _estimate_messages_tokens

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "File contents here."},
                ],
            },
        ]
        tokens = _estimate_messages_tokens(messages)
        assert tokens > 0

    def test_empty_messages(self) -> None:
        from app.agents.anthropic_runner import _estimate_messages_tokens

        assert _estimate_messages_tokens([]) == 0


class TestSummarizeConversation:
    @pytest.mark.asyncio
    async def test_below_threshold_returns_unchanged(self) -> None:
        from app.agents.anthropic_runner import _summarize_conversation

        messages = [{"role": "user", "content": "Short message."}]

        with patch("app.agents.anthropic_runner.settings") as mock_settings:
            mock_settings.AGENT_CONTEXT_SUMMARIZATION_THRESHOLD = 60_000
            result = await _summarize_conversation(messages, "system", 5)

        assert result is messages  # Same object — not a copy

    @pytest.mark.asyncio
    async def test_above_threshold_triggers_summarization(self) -> None:
        from app.agents.anthropic_runner import _summarize_conversation

        # Build messages with enough content to exceed a low threshold
        big_content = "x " * 500  # ~500 tokens
        messages = [
            {"role": "user", "content": big_content},
            {"role": "assistant", "content": big_content},
            {"role": "user", "content": big_content},
        ]

        summary_response = FakeResponse(
            content=[FakeTextBlock(text="## Summary\nThe conversation covered X, Y, Z.")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=200, output_tokens=50),
        )

        with (
            patch("app.agents.anthropic_runner.settings") as mock_settings,
            patch("app.agents.anthropic_runner.get_anthropic_client") as mock_gc,
        ):
            mock_settings.AGENT_CONTEXT_SUMMARIZATION_THRESHOLD = 100  # Very low
            mock_settings.MODEL_HAIKU = "claude-haiku-4-5-20251001"
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=summary_response)
            mock_gc.return_value = mock_client

            result = await _summarize_conversation(messages, "system prompt", 5)

        # Should return a compressed 2-message conversation
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert "Summary" in result[0]["content"]
        assert result[1]["role"] == "assistant"
        assert "Continuing" in result[1]["content"]

        # Haiku should have been called
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_summarization_failure_returns_original(self) -> None:
        from app.agents.anthropic_runner import _summarize_conversation

        big_content = "x " * 500
        messages = [{"role": "user", "content": big_content}]

        with (
            patch("app.agents.anthropic_runner.settings") as mock_settings,
            patch("app.agents.anthropic_runner.get_anthropic_client") as mock_gc,
        ):
            mock_settings.AGENT_CONTEXT_SUMMARIZATION_THRESHOLD = 100
            mock_settings.MODEL_HAIKU = "claude-haiku-4-5-20251001"
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=RuntimeError("API down"))
            mock_gc.return_value = mock_client

            result = await _summarize_conversation(messages, "system", 5)

        # Should gracefully return original messages
        assert result is messages

    @pytest.mark.asyncio
    async def test_empty_summary_returns_original(self) -> None:
        from app.agents.anthropic_runner import _summarize_conversation

        big_content = "x " * 500
        messages = [{"role": "user", "content": big_content}]

        empty_response = FakeResponse(
            content=[FakeTextBlock(text="")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=100, output_tokens=0),
        )

        with (
            patch("app.agents.anthropic_runner.settings") as mock_settings,
            patch("app.agents.anthropic_runner.get_anthropic_client") as mock_gc,
        ):
            mock_settings.AGENT_CONTEXT_SUMMARIZATION_THRESHOLD = 100
            mock_settings.MODEL_HAIKU = "claude-haiku-4-5-20251001"
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=empty_response)
            mock_gc.return_value = mock_client

            result = await _summarize_conversation(messages, "system", 5)

        assert result is messages


# ---------------------------------------------------------------------------
# Integration test: summarization triggered within run_agent loop
# ---------------------------------------------------------------------------


class TestRunAgentWithSummarization:
    @pytest.mark.asyncio
    async def test_short_run_never_summarizes(self) -> None:
        """Runs that finish in < 3 tool iterations never trigger summarization."""
        tool_response = FakeResponse(
            content=[
                FakeToolUseBlock(name="file_write", input={"path": "a.py", "content": "x"}, id="t1"),
            ],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=100, output_tokens=50),
        )
        end_response = FakeResponse(
            content=[FakeTextBlock(text="Done.")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=200, output_tokens=50),
        )
        mock_create = AsyncMock(side_effect=[tool_response, end_response])

        async def tool_executor(name: str, inp: dict[str, Any]) -> str:
            return "ok"

        with (
            patch("app.agents.anthropic_runner.get_anthropic_client") as mock_gc,
            patch("app.agents.anthropic_runner._summarize_conversation", wraps=lambda m, s, i: m) as mock_summarize,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_gc.return_value = mock_client

            result = await run_agent(
                system_prompt="test",
                user_message="test",
                tools=[FakeTool(name="file_write")],
                model="claude-sonnet-4-20250514",
                tool_executor=tool_executor,
                max_iterations=15,
            )

        # Only 2 iterations — check interval is 3, so summarization never called
        assert result.tool_loop_iterations == 2
        mock_summarize.assert_not_called()

    @pytest.mark.asyncio
    async def test_summarization_check_at_interval(self) -> None:
        """At iteration 3 (index 2), summarization check is triggered."""
        # 3 tool_use responses + 1 end_turn = 4 iterations
        tool_response = FakeResponse(
            content=[
                FakeToolUseBlock(name="web_search", input={"q": "x"}, id="t1"),
            ],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=500, output_tokens=100),
        )
        end_response = FakeResponse(
            content=[FakeTextBlock(text="Done.")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=600, output_tokens=80),
        )
        mock_create = AsyncMock(
            side_effect=[tool_response, tool_response, tool_response, end_response]
        )

        async def tool_executor(name: str, inp: dict[str, Any]) -> str:
            return "search result"

        # Mock _summarize_conversation to track calls but return messages unchanged
        original_messages = None

        async def mock_summarize(messages, system, iteration):
            nonlocal original_messages
            original_messages = list(messages)
            return messages  # No-op

        with (
            patch("app.agents.anthropic_runner.get_anthropic_client") as mock_gc,
            patch(
                "app.agents.anthropic_runner._summarize_conversation",
                side_effect=mock_summarize,
            ) as mock_sum,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = mock_create
            mock_gc.return_value = mock_client

            result = await run_agent(
                system_prompt="test",
                user_message="test",
                tools=[FakeTool(name="web_search")],
                model="claude-sonnet-4-20250514",
                tool_executor=tool_executor,
                max_iterations=15,
            )

        assert result.tool_loop_iterations == 4
        # _summarize_conversation should be called once (at iteration index 2, i.e., 3rd)
        assert mock_sum.call_count == 1
