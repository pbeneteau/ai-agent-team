"""
ToolSpec — native Anthropic tool abstraction.

Each ToolSpec pairs a JSON Schema (for the Anthropic API) with a Python executor
function that is called when the LLM uses that tool.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    """A tool that can be exposed to an Anthropic model and executed locally."""

    name: str
    description: str
    input_schema: dict
    executor: Callable[..., str]

    def to_anthropic(self) -> dict:
        """Return the Anthropic API tool definition dict."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    async def execute(self, tool_input: dict) -> str:
        """Invoke the executor in a thread pool; always returns a string."""
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: self.executor(**tool_input))
            return str(result)
        except TypeError as exc:
            logger.warning("Tool '%s' received invalid arguments %s: %s", self.name, tool_input, exc)
            return f"ERROR: invalid arguments for tool '{self.name}': {exc}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tool '%s' raised an exception: %s", self.name, exc)
            return f"ERROR: tool '{self.name}' failed: {exc}"
