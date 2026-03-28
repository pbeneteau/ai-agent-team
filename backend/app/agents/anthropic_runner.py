"""Agent execution loop — the core message loop that drives every agent call.

Ref: TDD-03 Section 6.4 (execution loop pseudocode),
     TDD-03 Section 7.3 (assumption extraction),
     TDD-03 Section 4.4 (output format / source citations).

Every agent in the system — learning, execution, reflection, sufficiency,
compilation — flows through ``run_agent()``.  The function sends messages to
the Anthropic API, processes tool-use responses in a loop, and returns a
typed ``AgentResult`` when the model signals ``end_turn``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Protocol

import anthropic
from anthropic import AsyncAnthropic, RateLimitError, APIStatusError

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level compiled regex patterns (TDD-03 Section 7.3)
# ---------------------------------------------------------------------------

ASSUMPTION_PATTERN: re.Pattern[str] = re.compile(
    r"\[ASSUMPTION:\s*(.+?)\]", re.IGNORECASE
)
TBD_PATTERN: re.Pattern[str] = re.compile(
    r"\[TBD:\s*(.+?)\]", re.IGNORECASE
)
SOURCE_PATTERN: re.Pattern[str] = re.compile(
    r"\[Source:\s*(.+?)\]", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Tool executor protocol
# ---------------------------------------------------------------------------

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]
"""Async callable: (tool_name, tool_input) -> result string.

The orchestrator provides a single dispatch function that routes tool calls
to the correct executor based on name.  This keeps the runner decoupled from
concrete tool implementations (Ticket 3.2 builds the actual executors).
"""


class ToolSpec(Protocol):
    """Minimal interface for a tool definition passed to the Anthropic API.

    Concrete implementations are built in Ticket 3.2 (tool registry).
    The runner only needs ``to_anthropic()`` to serialize the tool for the
    API call, and ``name`` for logging/dispatch.
    """

    @property
    def name(self) -> str: ...

    def to_anthropic(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Immutable result returned by ``run_agent()``.

    Attributes:
        text: Final text output extracted from the model's ``end_turn`` response.
        files: Files written via the ``file_write`` tool during the loop.
               Mapping of ``{relative_path: content}``.
        input_tokens: Cumulative input tokens across all API calls in the loop.
        output_tokens: Cumulative output tokens across all API calls in the loop.
        assumptions: Extracted ``[ASSUMPTION: ...]`` and ``[TBD: ...]`` entries.
        sources: Extracted ``[Source: ...]`` entries.
    """

    text: str
    files: dict[str, str] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    assumptions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AgentMaxIterationError(Exception):
    """Raised when the agent loop exhausts ``max_iterations`` without the
    model signalling ``end_turn``.

    Carries diagnostic context so callers can log / surface useful info.
    """

    def __init__(
        self,
        message: str,
        *,
        iterations: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        super().__init__(message)
        self.iterations: int = iterations
        self.input_tokens: int = input_tokens
        self.output_tokens: int = output_tokens


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def extract_assumptions(text: str) -> list[str]:
    """Extract ``[ASSUMPTION: ...]`` and ``[TBD: ...]`` tags from agent output.

    Returns a flat list of strings.  TBD entries are prefixed with ``"TBD — "``
    to distinguish them from regular assumptions (TDD-03 Section 7.3).
    """
    results: list[str] = []
    for match in ASSUMPTION_PATTERN.finditer(text):
        results.append(match.group(1).strip())
    for match in TBD_PATTERN.finditer(text):
        results.append(f"TBD — {match.group(1).strip()}")
    return results


def extract_sources(text: str) -> list[str]:
    """Extract ``[Source: ...]`` citation tags from agent output."""
    return [match.group(1).strip() for match in SOURCE_PATTERN.finditer(text)]


def _extract_text_blocks(content: list[Any]) -> str:
    """Concatenate all ``text`` blocks from an Anthropic response's content."""
    parts: list[str] = []
    for block in content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Shared client (lazy singleton)
# ---------------------------------------------------------------------------

_client: AsyncAnthropic | None = None


def get_anthropic_client() -> AsyncAnthropic:
    """Return a module-level ``AsyncAnthropic`` client (created once)."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Agent execution loop (TDD-03 Section 6.4)
# ---------------------------------------------------------------------------

# Retry config for transient Anthropic errors (429 rate-limit, 529 overloaded).
_RETRY_DELAYS: list[float] = [1.0, 2.0, 4.0]  # exponential-ish backoff


async def run_agent(
    system_prompt: str,
    user_message: str,
    tools: list[Any],
    model: str,
    *,
    tool_executor: ToolExecutor | None = None,
    max_iterations: int = 15,
    max_tokens: int = 8192,
) -> AgentResult:
    """Run the agent message loop until the model signals ``end_turn``.

    This is the single entry point for every LLM-backed agent call in the
    system.  The loop sends messages to the Anthropic API, dispatches tool
    calls through *tool_executor*, appends tool results, and repeats until
    the model finishes or *max_iterations* is exhausted.

    Args:
        system_prompt: The system message (positions 1-3 per TDD-03 Section 4).
        user_message: The user message (positions 4-9).
        tools: List of ``ToolSpec`` objects.  Each must implement
               ``to_anthropic() -> dict`` and have a ``name`` attribute.
               Pass an empty list for tool-free calls (e.g. sufficiency check).
        model: Full Anthropic model ID (e.g. ``settings.MODEL_SONNET``).
        tool_executor: Async callable ``(tool_name, tool_input) -> result_str``.
                       Required when *tools* is non-empty.  The orchestrator
                       provides a dispatch function that routes to concrete
                       executors (Ticket 3.2).
        max_iterations: Safety cap on API round-trips.  Default 15 per TDD-03.
        max_tokens: ``max_tokens`` forwarded to the Anthropic API.

    Returns:
        ``AgentResult`` with extracted text, files, token counts, assumptions,
        and sources.

    Raises:
        AgentMaxIterationError: If the loop reaches *max_iterations* without
            the model signalling ``end_turn``.
        anthropic.AuthenticationError: Invalid API key.
        anthropic.BadRequestError: Malformed request (prompt too long, etc.).
    """
    client: AsyncAnthropic = get_anthropic_client()

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_message},
    ]

    # Files collected from file_write tool calls during the loop.
    written_files: dict[str, str] = {}

    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Build the tools payload once (empty list → omit from API call).
    anthropic_tools: list[dict[str, Any]] = [t.to_anthropic() for t in tools]

    for iteration in range(max_iterations):
        # ----- API call with retry on transient errors ----- #
        response = await _call_api_with_retry(
            client=client,
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=anthropic_tools if anthropic_tools else anthropic.NOT_GIVEN,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # ----- end_turn → extract and return ----- #
        if response.stop_reason == "end_turn":
            result_text: str = _extract_text_blocks(response.content)
            return AgentResult(
                text=result_text,
                files=written_files,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                assumptions=extract_assumptions(result_text),
                sources=extract_sources(result_text),
            )

        # ----- tool_use → execute tools, append results, continue ----- #
        if response.stop_reason == "tool_use":
            if tool_executor is None:
                raise RuntimeError(
                    "Model requested tool_use but no tool_executor was provided."
                )

            tool_results: list[dict[str, Any]] = []

            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue

                tool_name: str = block.name
                tool_input: dict[str, Any] = block.input

                logger.debug(
                    "Tool call: %s (iteration %d)", tool_name, iteration + 1
                )

                try:
                    result_str: str = await tool_executor(tool_name, tool_input)
                except Exception:
                    logger.exception("Tool %s raised an exception", tool_name)
                    result_str = f"Error: tool '{tool_name}' failed unexpectedly."

                # Intercept file_write calls to collect written files.
                if tool_name == "file_write":
                    file_path: str | None = tool_input.get("path")
                    file_content: str | None = tool_input.get("content")
                    if file_path is not None and file_content is not None:
                        written_files[file_path] = file_content

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    }
                )

            # Append the assistant response (with tool_use blocks) and
            # the user message (with tool_result blocks) per Anthropic spec.
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            continue

        # ----- unexpected stop_reason ----- #
        logger.warning(
            "Unexpected stop_reason '%s' at iteration %d — treating as end_turn",
            response.stop_reason,
            iteration + 1,
        )
        result_text = _extract_text_blocks(response.content)
        return AgentResult(
            text=result_text,
            files=written_files,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            assumptions=extract_assumptions(result_text),
            sources=extract_sources(result_text),
        )

    # ----- loop exhausted ----- #
    raise AgentMaxIterationError(
        f"Agent did not complete in {max_iterations} iterations",
        iterations=max_iterations,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )


# ---------------------------------------------------------------------------
# Internal: API call with retry on transient errors
# ---------------------------------------------------------------------------


async def _call_api_with_retry(
    *,
    client: AsyncAnthropic,
    model: str,
    max_tokens: int,
    system: str,
    messages: list[dict[str, Any]],
    tools: Any,
) -> Any:
    """Send a single ``messages.create`` call, retrying on 429/529.

    Uses a short exponential backoff sequence (1s, 2s, 4s).  If all retries
    are exhausted the final exception propagates to the caller.

    Non-transient errors (400, 401, etc.) are raised immediately.
    """
    import asyncio

    last_exc: Exception | None = None

    for attempt, delay in enumerate([0.0] + _RETRY_DELAYS):
        if delay > 0:
            logger.info(
                "Retrying Anthropic API call (attempt %d) after %.1fs",
                attempt + 1,
                delay,
            )
            await asyncio.sleep(delay)

        try:
            return await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
        except RateLimitError as exc:
            logger.warning("Rate limited (429): %s", exc)
            last_exc = exc
            continue
        except APIStatusError as exc:
            if exc.status_code == 529:
                logger.warning("Anthropic overloaded (529): %s", exc)
                last_exc = exc
                continue
            # Non-transient — propagate immediately.
            raise

    # All retries exhausted.
    assert last_exc is not None
    raise last_exc
