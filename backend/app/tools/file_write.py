"""file_write tool — writes to the in-memory execution scratchpad.

Ref: TDD-03 Section 6.3 (file_read / file_write).
Files written here become the artifact version's file bundle uploaded to S3
at the end of execution.
"""

from __future__ import annotations

from typing import Any

from app.tools.registry import ExecutionContext, ToolDef


async def execute(tool_input: dict[str, Any], context: ExecutionContext) -> str:
    """Write a file to the in-memory scratchpad."""
    path: str = tool_input.get("path", "")
    content: str | None = tool_input.get("content")

    if not path:
        return "Error: 'path' is required."
    if content is None:
        return "Error: 'content' is required."

    context.files[path] = content
    return f"Wrote {len(content)} characters to '{path}'."


FILE_WRITE_TOOL = ToolDef(
    name="file_write",
    description="Write content to a file in your workspace. Use this to produce your output files.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative file path (e.g., 'src/index.ts')",
            },
            "content": {
                "type": "string",
                "description": "File content",
            },
        },
        "required": ["path", "content"],
    },
    executor=execute,
)
