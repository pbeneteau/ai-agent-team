"""Unit tests for Ticket 3.2 — tool definitions and executors.

Verify section:
  1. web_browser extracts text from a sample HTML string.
  2. file_write stores content, file_read retrieves it.
  3. get_tools_for_phase("execution", [...], [...]) returns all tools.
  4. get_tools_for_phase("reflection", [], []) returns only file tools.
"""

import asyncio

import pytest

from app.tools.registry import (
    ExecutionContext,
    ToolDef,
    create_tool_executor,
    get_tools_for_phase,
)
from app.tools.file_read import execute as file_read_execute
from app.tools.file_write import execute as file_write_execute
from app.tools.web_browser import extract_text


# ---------------------------------------------------------------------------
# Verify 1: web_browser extracts text from sample HTML
# ---------------------------------------------------------------------------


class TestWebBrowserExtract:
    def test_extracts_text_from_html(self) -> None:
        html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <nav>Navigation links</nav>
            <main>
                <h1>Hello World</h1>
                <p>This is a test paragraph with useful info.</p>
            </main>
            <footer>Footer content here</footer>
            <script>var x = 1;</script>
            <style>.hidden { display: none; }</style>
        </body>
        </html>
        """
        text = extract_text(html)
        assert "Hello World" in text
        assert "This is a test paragraph" in text
        # Non-content elements should be stripped
        assert "var x = 1" not in text
        assert "Navigation links" not in text
        assert "Footer content here" not in text
        assert "display: none" not in text

    def test_truncates_at_8000_chars(self) -> None:
        long_html = f"<html><body><p>{'x' * 10_000}</p></body></html>"
        text = extract_text(long_html)
        assert "[Content truncated at 8,000 characters]" in text
        # Total length: 8000 chars + truncation message + newlines
        assert len(text) < 8_100

    def test_handles_empty_html(self) -> None:
        text = extract_text("<html><body></body></html>")
        assert text == ""


# ---------------------------------------------------------------------------
# Verify 2: file_write stores content, file_read retrieves it
# ---------------------------------------------------------------------------


class TestFileTools:
    def test_write_then_read(self) -> None:
        context = ExecutionContext()

        # Write a file
        result = asyncio.run(
            file_write_execute(
                {"path": "src/main.py", "content": "print('hello')"},
                context,
            )
        )
        assert "Wrote" in result
        assert "src/main.py" in result

        # Read it back
        result = asyncio.run(
            file_read_execute({"path": "src/main.py"}, context)
        )
        assert result == "print('hello')"

    def test_write_overwrites(self) -> None:
        context = ExecutionContext()

        asyncio.run(
            file_write_execute(
                {"path": "a.txt", "content": "first"},
                context,
            )
        )
        asyncio.run(
            file_write_execute(
                {"path": "a.txt", "content": "second"},
                context,
            )
        )

        result = asyncio.run(file_read_execute({"path": "a.txt"}, context))
        assert result == "second"

    def test_read_nonexistent_returns_error(self) -> None:
        context = ExecutionContext()
        result = asyncio.run(
            file_read_execute({"path": "missing.txt"}, context)
        )
        assert "Error" in result
        assert "not found" in result

    def test_read_lists_available_files(self) -> None:
        context = ExecutionContext(files={"a.txt": "a", "b.txt": "b"})
        result = asyncio.run(
            file_read_execute({"path": "missing.txt"}, context)
        )
        assert "a.txt" in result
        assert "b.txt" in result

    def test_write_missing_path(self) -> None:
        context = ExecutionContext()
        result = asyncio.run(
            file_write_execute({"path": "", "content": "x"}, context)
        )
        assert "Error" in result

    def test_read_missing_path(self) -> None:
        context = ExecutionContext()
        result = asyncio.run(file_read_execute({"path": ""}, context))
        assert "Error" in result


# ---------------------------------------------------------------------------
# Verify 3 & 4: get_tools_for_phase returns correct tool subsets
# ---------------------------------------------------------------------------


class _MockMcpConnection:
    """Minimal stand-in for McpConnection model."""

    def __init__(self) -> None:
        self.name = "test_server"
        self.server_url = "http://localhost:8080"
        self.auth_config_encrypted = None
        self.discovered_tools = [
            {
                "name": "query",
                "description": "Run a query",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]


class _MockGitConnection:
    """Minimal stand-in for GitProviderConnection model."""

    def __init__(self) -> None:
        self.provider = "github"
        self.display_name = "My GitHub"
        self.access_token_encrypted = "fake-token"
        self.repositories = [{"full_name": "owner/repo"}]


class TestGetToolsForPhase:
    def test_execution_returns_all_tools(self) -> None:
        """Verify 3: execution phase with MCP + git returns all tool types."""
        tools = get_tools_for_phase(
            "execution",
            [_MockMcpConnection()],
            [_MockGitConnection()],
        )
        names = {t.name for t in tools}

        # All base tools
        assert "file_read" in names
        assert "file_write" in names
        assert "web_search" in names
        assert "web_browser" in names
        assert "vector_search" in names
        # Git tools
        assert "git_clone" in names
        assert "git_push" in names
        # MCP tools (dynamically named)
        assert any(n.startswith("mcp_") for n in names)

    def test_reflection_returns_only_file_tools(self) -> None:
        """Verify 4: reflection phase returns only file_read and file_write."""
        tools = get_tools_for_phase("reflection", [], [])
        names = {t.name for t in tools}
        assert names == {"file_read", "file_write"}

    def test_learning_includes_web_and_vector(self) -> None:
        """Learning gets web tools but NOT MCP or git."""
        tools = get_tools_for_phase("learning", [], [])
        names = {t.name for t in tools}
        assert "file_read" in names
        assert "file_write" in names
        assert "web_search" in names
        assert "web_browser" in names
        assert "vector_search" in names
        assert "git_clone" not in names
        assert "git_push" not in names
        assert not any(n.startswith("mcp_") for n in names)

    def test_execution_without_connections(self) -> None:
        """Execution without git/mcp connections omits those tools."""
        tools = get_tools_for_phase("execution", [], [])
        names = {t.name for t in tools}
        assert "file_read" in names
        assert "web_search" in names
        assert "git_clone" not in names
        assert not any(n.startswith("mcp_") for n in names)


# ---------------------------------------------------------------------------
# ToolDef protocol compliance
# ---------------------------------------------------------------------------


class TestToolDef:
    def test_to_anthropic_format(self) -> None:
        async def noop(i: dict, c: ExecutionContext) -> str:
            return ""

        tool = ToolDef(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            executor=noop,
        )
        payload = tool.to_anthropic()
        assert payload == {
            "name": "test_tool",
            "description": "A test tool",
            "input_schema": {"type": "object", "properties": {}},
        }

    def test_name_property(self) -> None:
        async def noop(i: dict, c: ExecutionContext) -> str:
            return ""

        tool = ToolDef(name="my_tool", description="", input_schema={}, executor=noop)
        assert tool.name == "my_tool"


# ---------------------------------------------------------------------------
# create_tool_executor dispatch
# ---------------------------------------------------------------------------


class TestCreateToolExecutor:
    def test_dispatch_known_tool(self) -> None:
        async def echo(tool_input: dict, context: ExecutionContext) -> str:
            return f"echo: {tool_input.get('msg', '')}"

        tool = ToolDef(name="echo", description="", input_schema={}, executor=echo)
        context = ExecutionContext()
        dispatch = create_tool_executor([tool], context)

        result = asyncio.run(dispatch("echo", {"msg": "hello"}))
        assert result == "echo: hello"

    def test_dispatch_unknown_tool(self) -> None:
        context = ExecutionContext()
        dispatch = create_tool_executor([], context)

        result = asyncio.run(dispatch("nonexistent", {}))
        assert "Error" in result
        assert "unknown tool" in result

    def test_dispatch_handles_executor_exception(self) -> None:
        async def explode(tool_input: dict, context: ExecutionContext) -> str:
            raise RuntimeError("boom")

        tool = ToolDef(name="bomb", description="", input_schema={}, executor=explode)
        context = ExecutionContext()
        dispatch = create_tool_executor([tool], context)

        result = asyncio.run(dispatch("bomb", {}))
        assert "Error" in result
        assert "failed unexpectedly" in result
