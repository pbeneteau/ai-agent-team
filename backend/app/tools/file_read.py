"""file_read tool — reads from the in-memory execution scratchpad.

Ref: TDD-03 Section 6.3 (file_read / file_write).
The scratchpad is an in-memory dict scoped to a single agent execution.
"""

from __future__ import annotations

from typing import Any

from app.tools.registry import ExecutionContext, ToolDef


async def execute(tool_input: dict[str, Any], context: ExecutionContext) -> str:
    """Read a file from the in-memory scratchpad."""
    path: str = tool_input.get("path", "")
    if not path:
        return "Error: 'path' is required."

    content = context.files.get(path)
    if content is None:
        available = sorted(context.files.keys())
        if available:
            return (
                f"Error: file '{path}' not found in workspace. "
                f"Available files: {', '.join(available)}"
            )
        return f"Error: file '{path}' not found. The workspace is empty."

    return content


FILE_READ_TOOL = ToolDef(
    name="file_read",
    description="Read the content of a file from your workspace.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative file path (e.g., 'src/index.ts')",
            },
        },
        "required": ["path"],
    },
    executor=execute,
)
