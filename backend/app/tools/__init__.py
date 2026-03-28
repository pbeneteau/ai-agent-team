"""Agent tools package — all tool definitions and the registry.

Usage:
    from app.tools import get_tools_for_phase, create_tool_executor, ExecutionContext

    tools = get_tools_for_phase("execution", workspace_mcp, workspace_git)
    context = ExecutionContext(files={}, project_id="...", db_session=session)
    executor = create_tool_executor(tools, context)
    result = await executor("web_search", {"query": "..."})
"""

from app.tools.registry import (
    ExecutionContext,
    Phase,
    ToolDef,
    create_tool_executor,
    get_tools_for_phase,
)

__all__ = [
    "ExecutionContext",
    "Phase",
    "ToolDef",
    "create_tool_executor",
    "get_tools_for_phase",
]
