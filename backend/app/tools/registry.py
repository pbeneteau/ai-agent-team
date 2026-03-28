"""Tool registry — ToolDef, ExecutionContext, and phase-based tool selection.

Ref: TDD-03 Section 6.1-6.3 (tool definitions and availability matrix).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

Phase = Literal["learning", "execution", "reflection"]

ToolExecutorFn = Callable[[dict[str, Any], "ExecutionContext"], Awaitable[str]]


@dataclass
class ExecutionContext:
    """Shared mutable state passed to every tool executor during a single agent run.

    Attributes:
        files: In-memory scratchpad for file_read/file_write. Scoped to one execution.
        project_id: Current project ID (used by vector_search for document scoping).
        db_session: Async SQLAlchemy session for database-backed tools.
        git_connections: GitProviderConnection model instances for the workspace.
        mcp_connections: McpConnection model instances for the workspace.
    """

    files: dict[str, str] = field(default_factory=dict)
    project_id: str | None = None
    db_session: AsyncSession | None = None
    git_connections: list[Any] = field(default_factory=list)
    mcp_connections: list[Any] = field(default_factory=list)


class ToolDef:
    """A tool definition paired with its executor. Satisfies the ToolSpec protocol.

    The ``to_anthropic()`` method serializes the schema for the Anthropic API.
    The ``executor`` is the async function that actually runs the tool.
    """

    __slots__ = ("_name", "description", "input_schema", "executor")

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        executor: ToolExecutorFn,
    ) -> None:
        self._name = name
        self.description = description
        self.input_schema = input_schema
        self.executor = executor

    @property
    def name(self) -> str:
        return self._name

    def to_anthropic(self) -> dict[str, Any]:
        """Serialize to the Anthropic tool-use format."""
        return {
            "name": self._name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def __repr__(self) -> str:
        return f"ToolDef(name={self._name!r})"


def get_tools_for_phase(
    phase: Phase,
    workspace_mcp: list[Any] | None = None,
    workspace_git: list[Any] | None = None,
) -> list[ToolDef]:
    """Return the correct tool subset for the given execution phase.

    Ref: TDD-03 Section 6.2 — tool availability matrix.

    +---------------+----------+-----------+------------+
    | Tool          | Learning | Execution | Reflection |
    +---------------+----------+-----------+------------+
    | file_read     | Yes      | Yes       | Yes        |
    | file_write    | Yes      | Yes       | Yes        |
    | web_search    | Yes      | Yes       | No         |
    | web_browser   | Yes      | Yes       | No         |
    | vector_search | Yes      | Yes       | No         |
    | mcp_*         | No       | Yes       | No         |
    | git_clone     | No       | Yes       | No         |
    | git_push      | No       | Yes       | No         |
    +---------------+----------+-----------+------------+
    """
    from app.tools.file_read import FILE_READ_TOOL
    from app.tools.file_write import FILE_WRITE_TOOL
    from app.tools.git_tools import GIT_CLONE_TOOL, GIT_PUSH_TOOL
    from app.tools.mcp_call import build_mcp_tools
    from app.tools.vector_search import VECTOR_SEARCH_TOOL
    from app.tools.web_browser import WEB_BROWSER_TOOL
    from app.tools.web_search import WEB_SEARCH_TOOL

    workspace_mcp = workspace_mcp or []
    workspace_git = workspace_git or []

    # Base: file tools available in all phases
    tools: list[ToolDef] = [FILE_READ_TOOL, FILE_WRITE_TOOL]

    # Learning and execution get web + vector search
    if phase in ("learning", "execution"):
        tools += [WEB_SEARCH_TOOL, WEB_BROWSER_TOOL, VECTOR_SEARCH_TOOL]

    # Execution only: MCP + git
    if phase == "execution":
        tools += build_mcp_tools(workspace_mcp)
        if workspace_git:
            tools += [GIT_CLONE_TOOL, GIT_PUSH_TOOL]

    return tools


def create_tool_executor(
    tools: list[ToolDef],
    context: ExecutionContext,
) -> Callable[[str, dict[str, Any]], Awaitable[str]]:
    """Build a dispatch function that routes tool calls to the correct executor.

    Returns a callable matching the ``ToolExecutor`` protocol from
    ``anthropic_runner``: ``async (tool_name, tool_input) -> result_str``.
    """
    executor_map: dict[str, ToolExecutorFn] = {
        tool.name: tool.executor for tool in tools
    }

    async def dispatch(tool_name: str, tool_input: dict[str, Any]) -> str:
        fn = executor_map.get(tool_name)
        if fn is None:
            return (
                f"Error: unknown tool '{tool_name}'. "
                f"Available tools: {', '.join(sorted(executor_map))}"
            )
        try:
            return await fn(tool_input, context)
        except Exception as exc:
            logger.exception("Unhandled exception in tool '%s'", tool_name)
            return f"Error: tool '{tool_name}' failed unexpectedly: {exc}"

    return dispatch
