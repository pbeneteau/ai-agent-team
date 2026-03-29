"""code_exec tool — run shell commands against artifact code in a sandboxed temp directory.

Ref: Ticket 17.5 (AD-29).

Gives review leads the ability to execute code (run tests, lint, type-check,
build) to verify functional correctness rather than relying on code reading
alone.

Security model:
  - Each call gets a fresh temp directory (no persistent state between calls).
  - Files from ``context.files`` are materialized into the temp dir (read-only
    snapshot — results are NOT written back to ``context.files``).
  - 30-second timeout via ``asyncio.wait_for``.
  - Output truncated to prevent context bloat (8K stdout + 4K stderr).
  - On Linux, ``unshare --net`` isolates network access.
  - On macOS (dev), network isolation is skipped with a warning.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.tools.registry import ExecutionContext, ToolDef

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS: int = settings.AGENT_CODE_EXEC_TIMEOUT
_STDOUT_MAX_CHARS = 8_000
_STDERR_MAX_CHARS = 4_000


async def execute(tool_input: dict[str, Any], context: ExecutionContext) -> str:
    """Execute a shell command in a sandboxed temp directory containing artifact files."""
    command: str = tool_input.get("command", "").strip()
    if not command:
        return "Error: 'command' is required."

    working_dir: str = tool_input.get("working_dir", ".").strip() or "."

    temp_dir: str | None = None
    try:
        # 1. Materialize context.files into a fresh temp directory
        temp_dir = tempfile.mkdtemp(prefix="code_exec_")
        for file_path, content in context.files.items():
            full_path = Path(temp_dir) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

        # Resolve working directory
        cwd = Path(temp_dir) / working_dir
        if not cwd.is_dir():
            cwd.mkdir(parents=True, exist_ok=True)

        # 2. Build the command with optional network isolation
        if platform.system() == "Linux":
            shell_cmd = f"unshare --net -- sh -c {_shell_quote(command)}"
        else:
            if platform.system() == "Darwin":
                logger.debug("code_exec: macOS — network isolation skipped")
            shell_cmd = command

        # 3. Run via subprocess
        process = await asyncio.create_subprocess_shell(
            shell_cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_sandbox_env(),
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return f"Error: command timed out after {_TIMEOUT_SECONDS} seconds."

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        # 4. Truncate output to prevent context bloat
        if len(stdout) > _STDOUT_MAX_CHARS:
            stdout = stdout[:_STDOUT_MAX_CHARS] + f"\n\n[stdout truncated at {_STDOUT_MAX_CHARS} chars]"
        if len(stderr) > _STDERR_MAX_CHARS:
            stderr = stderr[:_STDERR_MAX_CHARS] + f"\n\n[stderr truncated at {_STDERR_MAX_CHARS} chars]"

        return f"Exit code: {process.returncode}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

    except Exception as exc:
        logger.exception("code_exec failed")
        return f"Error: code_exec failed unexpectedly: {exc}"

    finally:
        # 5. Cleanup
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def _shell_quote(s: str) -> str:
    """Quote a string for safe use in sh -c."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _sandbox_env() -> dict[str, str]:
    """Build a minimal environment for the sandboxed process."""
    env = dict(os.environ)
    # Remove sensitive vars that might leak into the sandbox
    for key in ("ANTHROPIC_API_KEY", "SERPER_API_KEY", "VOYAGE_API_KEY",
                "S3_ACCESS_KEY", "S3_SECRET_KEY", "ENCRYPTION_KEY",
                "DATABASE_URL", "REDIS_URL"):
        env.pop(key, None)
    env["HOME"] = tempfile.gettempdir()
    return env


CODE_EXEC_TOOL = ToolDef(
    name="code_exec",
    description=(
        "Execute a shell command in a sandboxed environment containing the "
        "artifact's code files. Use this to run tests, lint, type-check, or "
        "attempt to build the code. 30-second timeout. Output is truncated "
        "to prevent context overflow."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute (e.g., 'python -m pytest', 'npm test', 'cat main.py').",
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory relative to project root. Defaults to '.'.",
                "default": ".",
            },
        },
        "required": ["command"],
    },
    executor=execute,
)
