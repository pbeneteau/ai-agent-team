"""
Tool registry — maps tool names to native ToolSpec instances.

Workspace-aware tools are scoped to the agent's provisioned workspace
directory and must never fall back to a shared temp directory.
"""
import json
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional
import logging

from app.config import get_settings, has_github_access
from app.config.tool_runtime import (
    GIT_CLONE_TIMEOUT_SECONDS,
    GIT_PULL_TIMEOUT_SECONDS,
    GIT_PROVIDER_RESULT_MAX_CHARS,
    MCP_TOOL_RESULT_MAX_CHARS,
    SKILL_CONSOLIDATION_INPUT_CHARS,
    SKILL_CONSOLIDATION_MAX_TOKENS,
    SKILL_CONSOLIDATION_TARGET_CHARS,
    SKILL_NOTE_CONSOLIDATE_AT,
    SKILL_NOTE_ENTRY_MAX_CHARS,
    SKILL_NOTE_MAX_CHARS,
    WORKSPACE_SHELL_TIMEOUT_SECONDS,
)
from app.core.git_provider_store import get_git_provider_store
from app.core.git_repo_runtime import (
    commit_and_push_changes,
    create_or_switch_branch,
    create_pull_request,
    ensure_repo_cloned,
    fetch_pull_request_context,
)
from app.core.git_providers import get_provider_display_name
from app.core.mcp_client import McpClientError, call_mcp_tool
from app.core.mcp_connection_store import get_mcp_connection_store
from app.core.workspace import resolve_workspace_path, resolve_workspace_root
from app.models.git_providers import AgentGitBinding
from app.models.mcp import AgentMcpToolBinding
from app.tools.spec import ToolSpec

logger = logging.getLogger(__name__)

_WEB_BROWSER_MAX_CHARS = 8_000
_GITHUB_SEARCH_MAX_RESULTS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_workspace_root(workspace_path: Optional[str], *, tool_name: str) -> Path:
    if not workspace_path:
        raise ValueError(f"{tool_name} requires an agent workspace_path.")
    root = resolve_workspace_root(workspace_path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_skill_name(skill_name: str) -> str:
    return skill_name.replace(" ", "_").replace("/", "_").lower()


def _is_reserved_project_context_skill(skill_name: str) -> bool:
    return _normalize_skill_name(skill_name) == "project_context"


def _slugify_tool_fragment(value: str) -> str:
    text = "".join(char.lower() if char.isalnum() else "_" for char in value.strip())
    return "_".join(part for part in text.split("_") if part) or "tool"


def _truncate_git_output(value: str) -> str:
    text = (value or "").strip()
    if len(text) > GIT_PROVIDER_RESULT_MAX_CHARS:
        return text[: GIT_PROVIDER_RESULT_MAX_CHARS - 1].rstrip() + "…"
    return text


# ---------------------------------------------------------------------------
# Workspace-scoped tool builders (ToolSpec)
# ---------------------------------------------------------------------------

def _build_file_read_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    root = _require_workspace_root(workspace_path, tool_name="file_read")

    def file_read(path: str) -> str:
        relative = (path or "").strip()
        if not relative:
            return "ERROR: path is required"
        try:
            target = resolve_workspace_path(root, relative)
        except PermissionError as exc:
            return f"ERROR: {exc}"
        if not target.exists():
            return f"ERROR: file not found: {relative}"
        if not target.is_file():
            return f"ERROR: not a file: {relative}"
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"ERROR: file is not valid UTF-8 text: {relative}"
        except Exception as exc:
            return f"ERROR: unable to read {relative}: {exc}"

    return ToolSpec(
        name="file_read",
        description="Read a UTF-8 text file from your workspace using a relative path.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Relative path to the file"}},
            "required": ["path"],
        },
        executor=file_read,
    )


def _build_file_write_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    root = _require_workspace_root(workspace_path, tool_name="file_write")

    def file_write(path: str, content: str) -> str:
        relative = (path or "").strip()
        if not relative:
            return "ERROR: path is required"
        try:
            target = resolve_workspace_path(root, relative)
        except PermissionError as exc:
            return f"ERROR: {exc}"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(content, encoding="utf-8")
        except Exception as exc:
            return f"ERROR: unable to write {relative}: {exc}"
        return f"Saved workspace file: {target.relative_to(root)}"

    return ToolSpec(
        name="file_write",
        description="Write a UTF-8 text file inside your workspace using a relative path.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to the file"},
                "content": {"type": "string", "description": "File content to write"},
            },
            "required": ["path", "content"],
        },
        executor=file_write,
    )


def _build_git_clone_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    root = _require_workspace_root(workspace_path, tool_name="git_clone")

    def git_clone(repo_url: str, folder_name: str = "") -> str:
        target_dir = resolve_workspace_path(root, "repos")
        target_dir.mkdir(parents=True, exist_ok=True)
        name = folder_name or repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
        try:
            target = resolve_workspace_path(root, str(Path("repos") / name))
        except PermissionError as exc:
            return f"ERROR: {exc}"
        if target.exists():
            result = subprocess.run(
                ["git", "-C", str(target), "pull", "--ff-only"],
                capture_output=True, text=True, timeout=GIT_PULL_TIMEOUT_SECONDS,
            )
        else:
            result = subprocess.run(
                ["git", "clone", "--depth=1", repo_url, str(target)],
                capture_output=True, text=True, timeout=GIT_CLONE_TIMEOUT_SECONDS,
            )
        if result.returncode != 0:
            return f"ERROR: {result.stderr}"
        return f"Repository available at: {target}"

    return ToolSpec(
        name="git_clone",
        description=(
            "Clone a git repository into the agent's workspace repos/ directory. "
            "SSH is the preferred protocol. Pass an optional folder_name to customize the directory name."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repo_url": {
                    "type": "string",
                    "description": "Git URL to clone (prefer SSH: git@github.com:user/repo.git)",
                },
                "folder_name": {
                    "type": "string",
                    "description": "Optional name for the local folder (defaults to repo name)",
                },
            },
            "required": ["repo_url"],
        },
        executor=git_clone,
    )


def _build_workspace_shell_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    root = _require_workspace_root(workspace_path, tool_name="workspace_shell")

    def workspace_shell(command: str, cwd: str = "") -> str:
        try:
            work_dir = resolve_workspace_path(root, cwd or ".")
        except PermissionError as exc:
            return f"ERROR: {exc}"
        work_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            command, shell=True, cwd=str(work_dir),
            capture_output=True, text=True, timeout=WORKSPACE_SHELL_TIMEOUT_SECONDS,
        )
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}"
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        output += f"\nExit code: {result.returncode}"
        return output or "(no output)"

    return ToolSpec(
        name="workspace_shell",
        description=(
            "Run a shell command inside the agent's workspace directory. "
            "Pass an optional cwd sub-directory to run from a specific folder."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "cwd": {
                    "type": "string",
                    "description": "Optional sub-directory within the workspace (e.g. 'repos/my-project')",
                },
            },
            "required": ["command"],
        },
        executor=workspace_shell,
    )


def _build_workspace_list_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    root = _require_workspace_root(workspace_path, tool_name="workspace_list")

    def workspace_list(sub_path: str = ".") -> str:
        try:
            target = resolve_workspace_path(root, sub_path or ".")
        except PermissionError as exc:
            return f"ERROR: {exc}"
        if not target.exists():
            return f"Path does not exist: {sub_path}"
        try:
            relative_target = target.relative_to(root)
            display_path = "." if str(relative_target) == "." else str(relative_target)
        except ValueError:
            display_path = "."
        lines = [f"Contents of {display_path}:\n"]
        for item in sorted(target.iterdir()):
            kind = "DIR " if item.is_dir() else "FILE"
            size = f"{item.stat().st_size:>10} B" if item.is_file() else " " * 12
            mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {kind}  {size}  {mtime}  {item.name}")
        return "\n".join(lines)

    return ToolSpec(
        name="workspace_list",
        description="List the contents of the agent's workspace directory.",
        input_schema={
            "type": "object",
            "properties": {
                "sub_path": {
                    "type": "string",
                    "description": "Sub-directory to list (default: workspace root '.')",
                }
            },
            "required": [],
        },
        executor=workspace_list,
    )


def _build_skill_note_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    root = _require_workspace_root(workspace_path, tool_name="skill_note")

    def skill_note(skill_name: str, insight: str) -> str:
        if not insight or len(insight.strip()) < 10:
            return "Insight too short — nothing saved."
        if _is_reserved_project_context_skill(skill_name):
            return "project_context est réservé au brief canonique. Utilise un autre skill pour noter un apprentissage."
        insight = insight.strip()[:SKILL_NOTE_ENTRY_MAX_CHARS]
        skills_dir = resolve_workspace_path(root, "skills")
        skills_dir.mkdir(parents=True, exist_ok=True)
        safe = _normalize_skill_name(skill_name)
        path = skills_dir / f"{safe}.md"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if insight[:60].lower() in existing.lower():
            return f"Insight already present in '{safe}' — nothing added."
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d")
        note_block = f"\n\n<!-- note:{timestamp} -->\n- {insight}"
        new_content = existing + note_block
        if len(new_content) > SKILL_NOTE_CONSOLIDATE_AT:
            consolidated = _consolidate_skill(safe, new_content, str(root))
            if consolidated:
                new_content = consolidated
        if len(new_content) > SKILL_NOTE_MAX_CHARS:
            return (
                f"Skill '{safe}' is full ({len(new_content)} chars). "
                "Consolidation was attempted but file remains large. "
                "Consider creating a new, focused skill file instead."
            )
        path.write_text(new_content, encoding="utf-8")
        return f"Insight appended to '{safe}' ({len(new_content)} chars total)."

    return ToolSpec(
        name="skill_note",
        description=(
            "Append a new, concise insight to one of your skill files. "
            "Use ONLY when you have discovered genuinely new information during a task. "
            "Keep the insight under 300 characters."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Which skill file to update (e.g. 'core_skills', 'project_context')",
                },
                "insight": {
                    "type": "string",
                    "description": "The new fact/insight to add — concise and specific",
                },
            },
            "required": ["skill_name", "insight"],
        },
        executor=skill_note,
    )


def _build_skill_write_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    root = _require_workspace_root(workspace_path, tool_name="skill_write")

    def skill_write(skill_name: str, content: str) -> str:
        skills_dir = resolve_workspace_path(root, "skills")
        skills_dir.mkdir(parents=True, exist_ok=True)
        safe = _normalize_skill_name(skill_name)
        if _is_reserved_project_context_skill(safe):
            return "project_context est dérivé du brief publié et ne peut pas être modifié avec skill_write."
        path = skills_dir / f"{safe}.md"
        header = (
            f"<!--\n"
            f"  skill: {safe}\n"
            f"  author: self\n"
            f"  updated: {datetime.now(UTC).isoformat()}Z\n"
            f"-->\n\n"
        )
        path.write_text(header + content, encoding="utf-8")
        return f"Skill '{safe}' saved to {path}"

    return ToolSpec(
        name="skill_write",
        description="Write or update a skill document in your own skills/ directory.",
        input_schema={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Short slug name for the skill (e.g. 'react_patterns', 'api_design')",
                },
                "content": {
                    "type": "string",
                    "description": "Full Markdown content of the skill document",
                },
            },
            "required": ["skill_name", "content"],
        },
        executor=skill_write,
    )


def _build_skill_read_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    root = _require_workspace_root(workspace_path, tool_name="skill_read")

    def skill_read(skill_name: str) -> str:
        skills_dir = resolve_workspace_path(root, "skills")
        safe = skill_name.replace(" ", "_").replace("/", "_").lower()
        path = skills_dir / f"{safe}.md"
        if not path.exists():
            available = [f.stem for f in skills_dir.glob("*.md")]
            return f"Skill '{safe}' not found. Available skills: {available}"
        return path.read_text(encoding="utf-8")

    return ToolSpec(
        name="skill_read",
        description="Read a skill document from your skills/ directory.",
        input_schema={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill to read (e.g. 'core_skills', 'react_patterns')",
                }
            },
            "required": ["skill_name"],
        },
        executor=skill_read,
    )


def _build_skill_list_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    root = _require_workspace_root(workspace_path, tool_name="skill_list")

    def skill_list() -> str:
        skills_dir = resolve_workspace_path(root, "skills")
        skills_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(skills_dir.glob("*.md"))
        if not files:
            return "No skills documented yet. Use skill_write to create your first skill."
        lines = [f"Your skills ({len(files)} total):\n"]
        for f in files:
            stat = f.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
            lines.append(f"  • {f.stem}  ({stat.st_size} B, updated {mtime})")
        return "\n".join(lines)

    return ToolSpec(
        name="skill_list",
        description="List all skill documents in your skills/ directory.",
        input_schema={"type": "object", "properties": {}, "required": []},
        executor=lambda: skill_list(),
    )


def _build_agent_skill_write_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    def agent_skill_write(agent_id: str, skill_name: str, content: str) -> str:
        from app.core.workspace import get_workspace_manager
        from app.core.agent_factory import get_agent_factory
        factory = get_agent_factory()
        agent = factory.get_agent(agent_id)
        if not agent:
            return f"ERROR: Agent '{agent_id}' not found."
        wm = get_workspace_manager()
        ws = wm.get(agent_id, agent.name, agent.title)
        if _is_reserved_project_context_skill(skill_name):
            return "ERROR: project_context est réservé au pipeline de briefing. Publiez le brief global à la place."
        path = ws.write_skill(skill_name, content, author="associate_alex")
        return f"Skill '{skill_name}' written for agent {agent.name} ({agent_id}) at {path}"

    return ToolSpec(
        name="agent_skill_write",
        description="Write a skill document into a specific team member's skills/ directory.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "The ID of the target agent"},
                "skill_name": {"type": "string", "description": "Short slug name for the skill"},
                "content": {"type": "string", "description": "Full Markdown content of the skill document"},
            },
            "required": ["agent_id", "skill_name", "content"],
        },
        executor=agent_skill_write,
    )


def _build_agent_skill_read_tool(workspace_path: Optional[str] = None) -> ToolSpec:
    def agent_skill_read(agent_id: str, skill_name: str) -> str:
        from app.core.workspace import get_workspace_manager
        from app.core.agent_factory import get_agent_factory
        factory = get_agent_factory()
        agent = factory.get_agent(agent_id)
        if not agent:
            return f"ERROR: Agent '{agent_id}' not found."
        wm = get_workspace_manager()
        ws = wm.get(agent_id, agent.name, agent.title)
        content = ws.read_skill(skill_name)
        if content is None:
            available = [s["name"] for s in ws.list_skills()]
            return f"Skill not found for agent {agent.name}. Available: {available}"
        return content

    return ToolSpec(
        name="agent_skill_read",
        description="Read a skill document from a specific team member's skills/ directory.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "The ID of the target agent"},
                "skill_name": {"type": "string", "description": "Name of the skill to read"},
            },
            "required": ["agent_id", "skill_name"],
        },
        executor=agent_skill_read,
    )


# ---------------------------------------------------------------------------
# Global tool builders
# ---------------------------------------------------------------------------

def _build_web_search_tool() -> Optional[ToolSpec]:
    def web_search(query: str) -> str:
        try:
            from duckduckgo_search import DDGS
            results = list(DDGS().text(query, max_results=5))
        except Exception as exc:
            return f"ERROR: web search failed: {exc}"
        if not results:
            return "No results found."
        parts = []
        for r in results:
            parts.append(f"**{r.get('title', 'No title')}**\n{r.get('href', '')}\n{r.get('body', '')}")
        return "\n\n---\n\n".join(parts)

    return ToolSpec(
        name="web_search",
        description="Search the web for information using a text query. Returns up to 5 results with title, URL, and snippet.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
        executor=web_search,
    )


def _build_web_browser_tool() -> Optional[ToolSpec]:
    def web_browser(url: str) -> str:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Agent-Team/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            return f"ERROR: unable to fetch URL '{url}': {exc}"
        # Strip <style> and <script> blocks, then all HTML tags
        text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > _WEB_BROWSER_MAX_CHARS:
            text = text[:_WEB_BROWSER_MAX_CHARS] + "… [truncated]"
        return text or "(no readable text found)"

    return ToolSpec(
        name="web_browser",
        description="Fetch and read the text content of a web page at the given URL.",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to fetch"}},
            "required": ["url"],
        },
        executor=web_browser,
    )


def _build_github_tool() -> Optional[ToolSpec]:
    settings = get_settings()
    if not has_github_access(settings):
        return None

    def github_search(query: str, search_type: str = "repositories") -> str:
        token = get_settings().github_token
        encoded_query = urllib.parse.quote(query)
        valid_types = ("repositories", "code", "issues", "commits")
        if search_type not in valid_types:
            search_type = "repositories"
        api_url = (
            f"https://api.github.com/search/{search_type}"
            f"?q={encoded_query}&per_page={_GITHUB_SEARCH_MAX_RESULTS}"
        )
        req = urllib.request.Request(
            api_url,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AI-Agent-Team/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            return f"ERROR: GitHub search failed: {exc}"
        items = data.get("items", [])
        if not items:
            return f"No {search_type} found for query: {query}"
        lines = [f"GitHub {search_type} search results for '{query}':"]
        for item in items:
            name = item.get("full_name") or item.get("name") or item.get("path") or "unknown"
            url = item.get("html_url", "")
            desc = item.get("description") or item.get("title") or ""
            lines.append(f"\n• {name}\n  {url}\n  {desc}")
        return "\n".join(lines)

    return ToolSpec(
        name="github",
        description=(
            "Search GitHub repositories, code, issues, or commits. "
            "search_type can be 'repositories', 'code', 'issues', or 'commits'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "GitHub search query"},
                "search_type": {
                    "type": "string",
                    "enum": ["repositories", "code", "issues", "commits"],
                    "description": "Type of GitHub search (default: repositories)",
                },
            },
            "required": ["query"],
        },
        executor=github_search,
    )


# code_execution and image_generation are retired — no native replacement
# Agents with these tool names will receive a graceful warning.

GLOBAL_TOOL_BUILDERS = {
    "web_search": _build_web_search_tool,
    "web_browser": _build_web_browser_tool,
    "github": _build_github_tool,
}

WORKSPACE_TOOL_BUILDERS = {
    "file_read": _build_file_read_tool,
    "file_write": _build_file_write_tool,
    "git_clone": _build_git_clone_tool,
    "workspace_shell": _build_workspace_shell_tool,
    "workspace_list": _build_workspace_list_tool,
    "skill_note": _build_skill_note_tool,
    "skill_write": _build_skill_write_tool,
    "skill_read": _build_skill_read_tool,
    "skill_list": _build_skill_list_tool,
    "agent_skill_write": _build_agent_skill_write_tool,
    "agent_skill_read": _build_agent_skill_read_tool,
}

_RETIRED_TOOLS = {"code_execution", "image_generation"}

_global_tool_cache: dict[str, Optional[ToolSpec]] = {}


# ---------------------------------------------------------------------------
# Skill consolidation (shared helper, used by skill_note)
# ---------------------------------------------------------------------------

def _consolidate_skill(skill_name: str, content: str, ws: str) -> Optional[str]:
    """Use Claude to deduplicate and compress a skill file that has grown too large."""
    try:
        import anthropic
        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=SKILL_CONSOLIDATION_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": (
                    f"The following is a skill document for an AI agent named '{skill_name}'.\n"
                    "It has grown large from accumulated notes. Please consolidate it:\n"
                    "- Remove duplicate or redundant entries\n"
                    "- Merge related facts into single bullet points\n"
                    "- Preserve ALL unique facts and insights\n"
                    f"- Keep the result under {SKILL_CONSOLIDATION_TARGET_CHARS} characters\n"
                    "- Return only the consolidated Markdown content, no preamble.\n\n"
                    f"---\n{content[:SKILL_CONSOLIDATION_INPUT_CHARS]}\n---"
                ),
            }],
        )
        from app.core.usage_tracker import get_usage_tracker
        get_usage_tracker().log(settings.claude_model, resp.usage.input_tokens, resp.usage.output_tokens)
        consolidated = resp.content[0].text.strip()
        logger.info("[skill_note] Consolidated '%s': %d → %d chars", skill_name, len(content), len(consolidated))
        return consolidated
    except Exception as exc:
        logger.warning("[skill_note] Consolidation failed for '%s': %s", skill_name, exc)
        return None


def consolidate_skill_content(skill_name: str, content: str, workspace_path: str) -> Optional[str]:
    """Public wrapper for compacting persisted skill content."""
    return _consolidate_skill(skill_name, content, workspace_path)


# ---------------------------------------------------------------------------
# MCP tool builder
# ---------------------------------------------------------------------------

def _build_mcp_tool(binding: AgentMcpToolBinding) -> Optional[ToolSpec]:
    store = get_mcp_connection_store()
    connection = store.get_connection(binding.connection_id)
    if connection is None or not connection.enabled or not binding.enabled:
        return None
    descriptors = {item.name: item for item in store.list_tools(binding.connection_id)}
    descriptor = descriptors.get(binding.tool_name)
    if descriptor is None or not descriptor.read_only:
        return None
    tool_name = binding.alias or (
        f"mcp__{_slugify_tool_fragment(connection.name)}__{_slugify_tool_fragment(binding.tool_name)}"
    )
    description = descriptor.description or "Call a user-configured MCP tool."
    schema_hint = descriptor.input_schema or {"type": "object", "properties": {}}
    full_description = (
        f"MCP tool from '{connection.name}'.\n\n"
        f"Original tool name: {binding.tool_name}\n"
        f"Description: {description}\n"
        "Pass ONE JSON object as a string in arguments_json matching this input schema:\n"
        f"{json.dumps(schema_hint, ensure_ascii=False)}"
    )

    def mcp_executor(arguments_json: str = "{}") -> str:
        try:
            parsed_arguments = json.loads(arguments_json or "{}")
        except Exception as exc:
            return f"ERROR: invalid JSON arguments for MCP tool '{binding.tool_name}': {exc}"
        if not isinstance(parsed_arguments, dict):
            return "ERROR: MCP tool arguments_json must decode to a JSON object."
        try:
            result = call_mcp_tool(connection, binding.tool_name, parsed_arguments)
            store.record_tool_call(connection.id, success=True)
            content = result.content.strip()
            if len(content) > MCP_TOOL_RESULT_MAX_CHARS:
                content = content[: MCP_TOOL_RESULT_MAX_CHARS - 1].rstrip() + "…"
            return content or "MCP tool returned no content."
        except McpClientError as exc:
            store.record_tool_call(connection.id, success=False, error=str(exc))
            return f"ERROR: MCP tool '{binding.tool_name}' failed: {exc}"
        except Exception as exc:
            store.record_tool_call(connection.id, success=False, error=str(exc))
            logger.exception("Unexpected MCP tool failure connection=%s tool=%s", connection.id, binding.tool_name)
            return f"ERROR: MCP tool '{binding.tool_name}' failed unexpectedly: {exc}"

    return ToolSpec(
        name=tool_name,
        description=full_description,
        input_schema={
            "type": "object",
            "properties": {
                "arguments_json": {
                    "type": "string",
                    "description": "JSON object string with arguments matching the MCP tool's input schema",
                }
            },
            "required": [],
        },
        executor=mcp_executor,
    )


def build_mcp_tools_for_agent(bindings: list[AgentMcpToolBinding] | None) -> list[ToolSpec]:
    tools: list[ToolSpec] = []
    for binding in bindings or []:
        spec = _build_mcp_tool(binding)
        if spec is not None:
            tools.append(spec)
    return tools


# ---------------------------------------------------------------------------
# Git provider tool builder
# ---------------------------------------------------------------------------

def build_git_tools_for_agent(
    bindings: list[AgentGitBinding] | None,
    workspace_path: Optional[str],
    *,
    allow_write: bool,
) -> list[ToolSpec]:
    store = get_git_provider_store()
    root = _require_workspace_root(workspace_path, tool_name="git_provider")
    tools: list[ToolSpec] = []

    for binding in bindings or []:
        if not binding.enabled:
            continue
        connection = store.get_connection(binding.connection_id)
        if connection is None or not connection.enabled:
            continue
        repo = store.get_repo(binding.connection_id, binding.repo_full_name)
        if repo is None:
            continue
        provider_name = get_provider_display_name(connection.provider)
        repo_key = _slugify_tool_fragment(binding.repo_full_name)
        branch_prefix = binding.branch_prefix.strip() or "agent"
        branch_prefix_slug = _slugify_tool_fragment(branch_prefix)

        # --- repo_clone ---
        def _make_clone(conn=connection, r=repo):
            def _exec(folder_name: str = "") -> str:
                try:
                    local_path = ensure_repo_cloned(root, conn, r, folder_name=folder_name)
                    store.record_action(conn.id, action="clone", success=True)
                    return f"Repository available at: {local_path}"
                except Exception as exc:
                    store.record_action(conn.id, action="clone", success=False, error=str(exc))
                    return f"ERROR: unable to clone repository '{r.full_name}': {exc}"
            return _exec

        tools.append(ToolSpec(
            name=f"repo_clone__{repo_key}",
            description=(
                f"Clone or refresh the authorized repository '{repo.full_name}' from {provider_name}. "
                f"Repository URL: {repo.web_url}. Default branch: {repo.default_branch}. "
                "Returns the local workspace path."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string", "description": "Optional local folder name"}
                },
                "required": [],
            },
            executor=_make_clone(),
        ))

        if allow_write:
            def _make_branch(conn=connection, r=repo, prefix=branch_prefix_slug):
                def _exec(branch_name: str, folder_name: str = "") -> str:
                    try:
                        local_path = ensure_repo_cloned(root, conn, r, folder_name=folder_name)
                        normalized = branch_name.strip() or f"{prefix}/work"
                        created = create_or_switch_branch(local_path, normalized, base_branch=r.default_branch)
                        return f"Current branch: {created}"
                    except Exception as exc:
                        return f"ERROR: unable to create branch for '{r.full_name}': {exc}"
                return _exec

            tools.append(ToolSpec(
                name=f"repo_branch__{repo_key}",
                description=(
                    f"Create or reset a dedicated working branch for '{repo.full_name}'. "
                    f"Protected branches like main/master are blocked. Suggested prefix: {branch_prefix_slug}."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "branch_name": {"type": "string", "description": "Branch name to create or switch to"},
                        "folder_name": {"type": "string", "description": "Optional local folder name"},
                    },
                    "required": ["branch_name"],
                },
                executor=_make_branch(),
            ))

        # --- repo_pr_context ---
        def _make_pr_context(conn=connection, r=repo):
            def _exec(number: int = 0) -> str:
                try:
                    content = fetch_pull_request_context(conn, repo=r, number=number if number > 0 else None)
                    return _truncate_git_output(content)
                except Exception as exc:
                    return f"ERROR: unable to fetch PR/MR context for '{r.full_name}': {exc}"
            return _exec

        tools.append(ToolSpec(
            name=f"repo_pr_context__{repo_key}",
            description=(
                f"Fetch pull request or merge request context for '{repo.full_name}' on {provider_name}. "
                "Pass a positive number for a specific PR/MR, or 0 to list open review requests."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "number": {"type": "integer", "description": "PR/MR number (0 = list open)"}
                },
                "required": [],
            },
            executor=_make_pr_context(),
        ))

        if allow_write and binding.can_push:
            def _make_commit(conn=connection, r=repo):
                def _exec(commit_message: str, branch_name: str, folder_name: str = "") -> str:
                    try:
                        local_path = ensure_repo_cloned(root, conn, r, folder_name=folder_name)
                        output = commit_and_push_changes(
                            local_path, connection=conn, repo=r,
                            commit_message=commit_message, branch_name=branch_name,
                        )
                        store.record_action(conn.id, action="push", success=True)
                        return _truncate_git_output(output)
                    except Exception as exc:
                        store.record_action(conn.id, action="push", success=False, error=str(exc))
                        return f"ERROR: unable to commit/push changes for '{r.full_name}': {exc}"
                return _exec

            tools.append(ToolSpec(
                name=f"repo_commit_push__{repo_key}",
                description=(
                    f"Commit and push local changes for '{repo.full_name}' on a dedicated branch. "
                    "Never use main/master. The branch must already exist."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "commit_message": {"type": "string", "description": "Git commit message"},
                        "branch_name": {"type": "string", "description": "Branch to push to"},
                        "folder_name": {"type": "string", "description": "Optional local folder name"},
                    },
                    "required": ["commit_message", "branch_name"],
                },
                executor=_make_commit(),
            ))

        if allow_write and binding.can_open_pr:
            def _make_open_pr(conn=connection, r=repo):
                def _exec(title: str, source_branch: str, body: str = "", target_branch: str = "") -> str:
                    try:
                        output = create_pull_request(
                            conn, repo=r, title=title, body=body,
                            source_branch=source_branch,
                            target_branch=target_branch or r.default_branch,
                        )
                        store.record_action(conn.id, action="pull_request", success=True)
                        return _truncate_git_output(output)
                    except Exception as exc:
                        store.record_action(conn.id, action="pull_request", success=False, error=str(exc))
                        return f"ERROR: unable to create PR/MR for '{r.full_name}': {exc}"
                return _exec

            tools.append(ToolSpec(
                name=f"repo_open_pr__{repo_key}",
                description=(
                    f"Open a pull request or merge request for '{repo.full_name}' on {provider_name}. "
                    f"Source branch must not be main/master. Target defaults to {repo.default_branch}."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "PR/MR title"},
                        "source_branch": {"type": "string", "description": "Branch with changes"},
                        "body": {"type": "string", "description": "PR/MR description (optional)"},
                        "target_branch": {"type": "string", "description": "Target branch (defaults to default branch)"},
                    },
                    "required": ["title", "source_branch"],
                },
                executor=_make_open_pr(),
            ))

    return tools


# ---------------------------------------------------------------------------
# Main entry point — native ToolSpec list
# ---------------------------------------------------------------------------

def get_tools_for_agent_native(
    tool_names: list[str],
    workspace_path: Optional[str] = None,
    git_bindings: list[AgentGitBinding] | None = None,
    mcp_tool_bindings: list[AgentMcpToolBinding] | None = None,
    allow_git_write: bool = False,
) -> list[ToolSpec]:
    """Build a list of ToolSpec for an agent — no CrewAI dependency."""
    specs: list[ToolSpec] = []

    for name in tool_names:
        if name in _RETIRED_TOOLS:
            logger.warning("Tool '%s' is retired and not available in the native runner.", name)
            continue

        if name in WORKSPACE_TOOL_BUILDERS:
            try:
                spec = WORKSPACE_TOOL_BUILDERS[name](workspace_path)
                specs.append(spec)
            except Exception as exc:
                logger.error("Failed to build workspace tool '%s': %s", name, exc)
                raise

        elif name in GLOBAL_TOOL_BUILDERS:
            if name not in _global_tool_cache:
                try:
                    _global_tool_cache[name] = GLOBAL_TOOL_BUILDERS[name]()
                except Exception as exc:
                    logger.error("Failed to build global tool '%s': %s", name, exc)
                    _global_tool_cache[name] = None
            spec = _global_tool_cache.get(name)
            if spec is not None:
                specs.append(spec)

        else:
            logger.warning("Unknown tool: '%s'", name)

    specs.extend(build_git_tools_for_agent(git_bindings, workspace_path, allow_write=allow_git_write))
    specs.extend(build_mcp_tools_for_agent(mcp_tool_bindings))
    return specs
