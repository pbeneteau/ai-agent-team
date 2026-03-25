"""
AnthropicAgentRunner — native Anthropic agentic loop.

Replaces CrewAI's Crew/Task/kickoff pattern with a direct AsyncAnthropic
messages loop that supports streaming and native tool_use handling.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from anthropic import AsyncAnthropic

from app.tools.spec import ToolSpec

logger = logging.getLogger(__name__)

# Sentinel stop reasons that mean the agent is done (no more tool calls)
_TERMINAL_STOP_REASONS = {"end_turn", "stop_sequence"}


class AnthropicAgentRunner:
    """
    Runs an agentic loop against the Anthropic API.

    Each call to `run()`:
    1. Sends system_prompt + user_message to the model.
    2. If the response contains tool_use blocks, executes them and sends results back.
    3. Repeats until end_turn, max_tokens, or max_iter is reached.
    4. Optionally streams text tokens to `on_text_chunk` as they arrive.
    """

    def __init__(self, client: AsyncAnthropic) -> None:
        self.client = client

    async def run(
        self,
        *,
        system_prompt: str,
        user_message: str,
        tools: list[ToolSpec],
        model: str,
        max_tokens: int,
        max_iter: int,
        on_text_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> tuple[str, int, int]:
        """
        Run the agentic loop.

        Returns:
            (result_text, total_input_tokens, total_output_tokens)

        Raises:
            AgentMaxIterError if the agent does not reach end_turn within max_iter steps.
            Any exception raised by the Anthropic API is propagated as-is.
        """
        messages: list[dict] = [{"role": "user", "content": user_message}]
        anthropic_tools = [t.to_anthropic() for t in tools]
        tool_map = {t.name: t for t in tools}
        total_input = 0
        total_output = 0

        for iteration in range(max_iter):
            logger.debug(
                "AgentRunner iteration %d/%d — model=%s tools=%d",
                iteration + 1, max_iter, model, len(tools),
            )

            if on_text_chunk is not None:
                # Streaming mode: forward text tokens as they arrive
                accumulated_text = ""
                async with self.client.messages.stream(
                    model=model,
                    system=system_prompt,
                    messages=messages,
                    tools=anthropic_tools or [],
                    max_tokens=max_tokens,
                ) as stream:
                    async for text_delta in stream.text_stream:
                        accumulated_text += text_delta
                        await on_text_chunk(text_delta)
                    response = await stream.get_final_message()
            else:
                response = await self.client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=messages,
                    tools=anthropic_tools or [],
                    max_tokens=max_tokens,
                )

            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            stop_reason = response.stop_reason

            if stop_reason in _TERMINAL_STOP_REASONS:
                result_text = "\n\n".join(
                    block.text for block in response.content if block.type == "text"
                ).strip()
                logger.debug(
                    "AgentRunner completed after %d iteration(s) — %d in / %d out tokens",
                    iteration + 1, total_input, total_output,
                )
                return result_text, total_input, total_output

            if stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    spec = tool_map.get(block.name)
                    if spec is not None:
                        logger.debug("AgentRunner executing tool '%s'", block.name)
                        result = await spec.execute(dict(block.input))
                    else:
                        logger.warning("AgentRunner: unknown tool '%s'", block.name)
                        result = f"ERROR: tool '{block.name}' is not available."
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

                # Append assistant response + tool results to the conversation
                messages.append({"role": "assistant", "content": list(response.content)})
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason (max_tokens, etc.) — treat as partial result
            logger.warning(
                "AgentRunner: unexpected stop_reason '%s' at iteration %d",
                stop_reason, iteration + 1,
            )
            partial_text = "\n\n".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            if partial_text:
                return partial_text, total_input, total_output
            break

        raise AgentMaxIterError(
            f"Agent did not reach end_turn within {max_iter} iterations "
            f"({total_input} input / {total_output} output tokens consumed)."
        )


class AgentMaxIterError(RuntimeError):
    """Raised when the agent loop exhausts max_iter without completing."""
