"""
Tool registry — maps tool names to CrewAI-compatible tool instances.

Workspace-aware tools are scoped to the agent's provisioned workspace
directory and must never fall back to a shared temp directory.
"""
import json
import subprocess
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional
import logging

from crewai.tools import tool

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

logger = logging.getLogger(__name__)


def _require_workspace_root(workspace_path: Optional[str], *, tool_name: str) -> Path:
    if not workspace_path:
        raise ValueError(f"{tool_name} requires an agent workspace_path.")
    root = resolve_workspace_root(workspace_path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_web_search_tool():
    try:
        from crewai_tools import SerperDevTool
        return SerperDevTool()
    except Exception:
        try:
            from crewai_tools import EXASearchTool
            return EXASearchTool()
        except Exception as e:
            logger.warning(f"Web search tool unavailable: {e}")
            return None


def _build_file_read_tool(workspace_path: Optional[str] = None):
    root = _require_workspace_root(workspace_path, tool_name="file_read")

    @tool("file_read")
    def file_read(path: str) -> str:
        """Read a UTF-8 text file from your workspace using a relative path."""
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

    return file_read


def _build_file_write_tool(workspace_path: Optional[str] = None):
    root = _require_workspace_root(workspace_path, tool_name="file_write")

    @tool("file_write")
    def file_write(path: str, content: str) -> str:
        """Write a UTF-8 text file inside your workspace using a relative path."""
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

    return file_write


def _build_code_execution_tool():
    try:
        from crewai_tools import CodeInterpreterTool
        return CodeInterpreterTool()
    except Exception as e:
        logger.warning(f"CodeInterpreterTool unavailable: {e}")
        return None


def _build_github_tool():
    settings = get_settings()
    if not has_github_access(settings):
        return None
    try:
        from crewai_tools import GithubSearchTool
        return GithubSearchTool(gh_token=settings.github_token)
    except Exception as e:
        logger.warning(f"GithubSearchTool unavailable: {e}")
        return None


def _build_web_browser_tool():
    try:
        from crewai_tools import ScrapeWebsiteTool
        return ScrapeWebsiteTool()
    except Exception as e:
        logger.warning(f"Web browser tool unavailable: {e}")
        return None


def _build_image_generation_tool():
    try:
        from crewai_tools import DallETool
        return DallETool()
    except Exception as e:
        logger.warning(f"DallETool unavailable: {e}")
        return None


def _build_git_clone_tool(workspace_path: Optional[str] = None):
    """Custom tool that clones a repo into the agent's repos/ workspace folder."""

    root = _require_workspace_root(workspace_path, tool_name="git_clone")

    @tool("git_clone")
    def git_clone(repo_url: str, folder_name: str = "") -> str:
        """Clone a git repository into the agent's workspace repos/ directory.
        SSH is the preferred protocol — use SSH URLs whenever possible.
        Args:
            repo_url: The git URL to clone.
                      Prefer SSH:   git@github.com:user/repo.git
                      HTTPS also works: https://github.com/user/repo.git
            folder_name: Optional name for the target folder (defaults to repo name)
        Returns the path of the cloned directory.
        """
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

    return git_clone


def _build_workspace_shell_tool(workspace_path: Optional[str] = None):
    """Custom tool that runs shell commands inside the agent's workspace."""

    root = _require_workspace_root(workspace_path, tool_name="workspace_shell")

    @tool("workspace_shell")
    def workspace_shell(command: str, cwd: str = "") -> str:
        """Run a shell command inside the agent's workspace directory.
        Commands are executed in the workspace root (or a sub-path if cwd is specified).
        Args:
            command: Shell command to run (e.g. 'pip install -r requirements.txt')
            cwd: Optional sub-directory within the workspace to run from (e.g. 'repos/my-project')
        Returns stdout and stderr output.
        """
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

    return workspace_shell


def _normalize_skill_name(skill_name: str) -> str:
    return skill_name.replace(" ", "_").replace("/", "_").lower()


def _is_reserved_project_context_skill(skill_name: str) -> bool:
    return _normalize_skill_name(skill_name) == "project_context"


def _build_skill_note_tool(workspace_path: Optional[str] = None):
    """Append a concise insight to a skill file without overwriting it.
    Triggers automatic consolidation when the file gets too large."""

    root = _require_workspace_root(workspace_path, tool_name="skill_note")

    @tool("skill_note")
    def skill_note(skill_name: str, insight: str) -> str:
        """Append a new, concise insight to one of your skill files.

        Use this ONLY when you have discovered genuinely NEW information during a task
        that you did not already know (e.g., found via web search, inferred from data).
        Do NOT use this to repeat information already in your skills.
        Keep the insight under 300 characters — one focused fact or decision.

        Args:
            skill_name: Which skill file to update (e.g. 'core_skills', 'project_context',
                        or a topic slug like 'yc_requirements')
            insight:    The new fact/insight to add. Be concise and specific.
        Returns a confirmation or an explanation of why nothing was saved.
        """
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

        # Reject if the insight is already present (simple substring check)
        if insight[:60].lower() in existing.lower():
            return f"Insight already present in '{safe}' — nothing added."

        # Append note with timestamp
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d")
        note_block = f"\n\n<!-- note:{timestamp} -->\n- {insight}"
        new_content = existing + note_block

        # If file is getting too large, consolidate before writing
        if len(new_content) > SKILL_NOTE_CONSOLIDATE_AT:
            consolidated = _consolidate_skill(safe, new_content, str(root))
            if consolidated:
                new_content = consolidated

        # Hard cap — never exceed maximum
        if len(new_content) > SKILL_NOTE_MAX_CHARS:
            return (
                f"Skill '{safe}' is full ({len(new_content)} chars). "
                "Consolidation was attempted but file remains large. "
                "Consider creating a new, focused skill file instead."
            )

        path.write_text(new_content, encoding="utf-8")
        return f"Insight appended to '{safe}' ({len(new_content)} chars total)."

    return skill_note


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
        logger.info(f"[skill_note] Consolidated '{skill_name}': {len(content)} → {len(consolidated)} chars")
        return consolidated
    except Exception as e:
        logger.warning(f"[skill_note] Consolidation failed for '{skill_name}': {e}")
        return None


def consolidate_skill_content(skill_name: str, content: str, workspace_path: str) -> Optional[str]:
    """Public wrapper for compacting persisted skill content."""
    return _consolidate_skill(skill_name, content, workspace_path)


def _build_skill_write_tool(workspace_path: Optional[str] = None):
    """Tool for an agent to write/update one of its own skills."""

    root = _require_workspace_root(workspace_path, tool_name="skill_write")

    @tool("skill_write")
    def skill_write(skill_name: str, content: str) -> str:
        """Write or update a skill document in your own skills/ directory.
        Use this to document something you have learned, a methodology, or expertise area.
        Args:
            skill_name: Short slug name for the skill (e.g. 'react_patterns', 'api_design')
            content:    Full Markdown content of the skill document
        Returns a confirmation message.
        """
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

    return skill_write


def _build_skill_read_tool(workspace_path: Optional[str] = None):
    """Tool for an agent to read one of its own skills."""

    root = _require_workspace_root(workspace_path, tool_name="skill_read")

    @tool("skill_read")
    def skill_read(skill_name: str) -> str:
        """Read a skill document from your skills/ directory.
        Args:
            skill_name: Name of the skill to read (e.g. 'core_skills', 'react_patterns')
        Returns the full Markdown content of the skill.
        """
        skills_dir = resolve_workspace_path(root, "skills")
        safe = skill_name.replace(" ", "_").replace("/", "_").lower()
        path = skills_dir / f"{safe}.md"
        if not path.exists():
            available = [f.stem for f in skills_dir.glob("*.md")]
            return f"Skill '{safe}' not found. Available skills: {available}"
        return path.read_text(encoding="utf-8")

    return skill_read


def _build_skill_list_tool(workspace_path: Optional[str] = None):
    """Tool to list all skills in the agent's skills/ directory."""

    root = _require_workspace_root(workspace_path, tool_name="skill_list")

    @tool("skill_list")
    def skill_list() -> str:
        """List all skill documents in your skills/ directory.
        Returns a formatted list of available skills with metadata.
        """
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

    return skill_list


def _build_agent_skill_write_tool(workspace_path: Optional[str] = None):
    """
    Tool for the Associate (Alex) to write skills into ANY sub-agent's skills/ directory.
    This is a privileged tool — only given to the Associate agent.
    """
    @tool("agent_skill_write")
    def agent_skill_write(agent_id: str, skill_name: str, content: str) -> str:
        """Write a skill document into a specific team member's skills/ directory.
        Use this as the Associate to coach or document expertise for a sub-agent.
        Args:
            agent_id:   The ID of the target agent (get it from the team roster)
            skill_name: Short slug name for the skill
            content:    Full Markdown content of the skill document
        Returns a confirmation message.
        """
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

    return agent_skill_write


def _build_agent_skill_read_tool(workspace_path: Optional[str] = None):
    """Tool for the Associate to read a sub-agent's skill."""

    @tool("agent_skill_read")
    def agent_skill_read(agent_id: str, skill_name: str) -> str:
        """Read a skill document from a specific team member's skills/ directory.
        Args:
            agent_id:   The ID of the target agent
            skill_name: Name of the skill to read
        Returns the skill content.
        """
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

    return agent_skill_read


def _build_workspace_list_tool(workspace_path: Optional[str] = None):
    """Custom tool to list the contents of the agent's workspace."""

    root = _require_workspace_root(workspace_path, tool_name="workspace_list")

    @tool("workspace_list")
    def workspace_list(sub_path: str = ".") -> str:
        """List the contents of the agent's workspace directory.
        Args:
            sub_path: Sub-directory to list (default: workspace root)
        Returns a text listing of files and folders.
        """
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

    return workspace_list


# Tool builders that do NOT depend on workspace (shared/cached globally)
GLOBAL_TOOL_BUILDERS = {
    "web_search": _build_web_search_tool,
    "web_browser": _build_web_browser_tool,
    "image_generation": _build_image_generation_tool,
    "github": _build_github_tool,
    "code_execution": _build_code_execution_tool,
}

# Tool builders that ARE workspace-scoped (built per-agent, not cached globally)
WORKSPACE_TOOL_BUILDERS = {
    "file_read": _build_file_read_tool,
    "file_write": _build_file_write_tool,
    "git_clone": _build_git_clone_tool,
    "workspace_shell": _build_workspace_shell_tool,
    "workspace_list": _build_workspace_list_tool,
    # Skill tools — self
    "skill_note": _build_skill_note_tool,   # append-only, safe for self-augmentation
    "skill_write": _build_skill_write_tool,
    "skill_read": _build_skill_read_tool,
    "skill_list": _build_skill_list_tool,
    # Skill tools — cross-agent (Associate only)
    "agent_skill_write": _build_agent_skill_write_tool,
    "agent_skill_read": _build_agent_skill_read_tool,
}

_global_tool_cache: dict = {}


def _slugify_tool_fragment(value: str) -> str:
    text = "".join(char.lower() if char.isalnum() else "_" for char in value.strip())
    return "_".join(part for part in text.split("_") if part) or "tool"


def _build_mcp_tool(binding: AgentMcpToolBinding):
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
    tool_doc = (
        f"MCP tool from '{connection.name}'.\n\n"
        f"Original tool name: {binding.tool_name}\n"
        f"Description: {description}\n"
        "Pass ONE JSON object as a string in arguments_json matching this input schema:\n"
        f"{json.dumps(schema_hint, ensure_ascii=False)}"
    )

    @tool(tool_name)
    def mcp_tool(arguments_json: str = "{}") -> str:
        """Call a user-configured MCP tool using a JSON object string."""
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

    mcp_tool.__doc__ = tool_doc
    return mcp_tool


def build_mcp_tools_for_agent(bindings: list[AgentMcpToolBinding] | None) -> list:
    tools = []
    for binding in bindings or []:
        tool_obj = _build_mcp_tool(binding)
        if tool_obj is not None:
            tools.append(tool_obj)
    return tools


def _truncate_git_output(value: str) -> str:
    text = (value or "").strip()
    if len(text) > GIT_PROVIDER_RESULT_MAX_CHARS:
        return text[: GIT_PROVIDER_RESULT_MAX_CHARS - 1].rstrip() + "…"
    return text


def build_git_tools_for_agent(
    bindings: list[AgentGitBinding] | None,
    workspace_path: Optional[str],
    *,
    allow_write: bool,
) -> list:
    store = get_git_provider_store()
    root = _require_workspace_root(workspace_path, tool_name="git_provider")
    tools = []
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

        clone_doc = (
            f"Clone or refresh the authorized repository '{repo.full_name}' from {provider_name}. "
            f"Repository URL: {repo.web_url}. Default branch: {repo.default_branch}. "
            "Returns the local workspace path."
        )

        @tool(f"repo_clone__{repo_key}")
        def repo_clone_bound(folder_name: str = "") -> str:
            """Clone or refresh the authorized repository in the agent workspace."""
            try:
                local_path = ensure_repo_cloned(root, connection, repo, folder_name=folder_name)
                store.record_action(connection.id, action="clone", success=True)
                return f"Repository available at: {local_path}"
            except Exception as exc:
                store.record_action(connection.id, action="clone", success=False, error=str(exc))
                return f"ERROR: unable to clone repository '{repo.full_name}': {exc}"

        repo_clone_bound.__doc__ = clone_doc
        tools.append(repo_clone_bound)

        if allow_write:
            branch_doc = (
                f"Create or reset a dedicated working branch for '{repo.full_name}'. "
                f"Protected branches like main/master are blocked. Suggested prefix: {branch_prefix_slug}."
            )

            @tool(f"repo_branch__{repo_key}")
            def repo_create_branch(branch_name: str, folder_name: str = "") -> str:
                """Create or switch to a safe working branch on the authorized repository."""
                try:
                    local_path = ensure_repo_cloned(root, connection, repo, folder_name=folder_name)
                    normalized_branch = branch_name.strip() or f"{branch_prefix_slug}/work"
                    created_branch = create_or_switch_branch(
                        local_path,
                        normalized_branch,
                        base_branch=repo.default_branch,
                    )
                    return f"Current branch: {created_branch}"
                except Exception as exc:
                    return f"ERROR: unable to create branch for '{repo.full_name}': {exc}"

            repo_create_branch.__doc__ = branch_doc
            tools.append(repo_create_branch)

        pr_context_doc = (
            f"Fetch pull request or merge request context for '{repo.full_name}' on {provider_name}. "
            "Pass a positive number for a specific PR/MR, or 0 to list open review requests."
        )

        @tool(f"repo_pr_context__{repo_key}")
        def repo_fetch_pr_context(number: int = 0) -> str:
            """Fetch pull request or merge request context for the authorized repository."""
            try:
                content = fetch_pull_request_context(
                    connection,
                    repo=repo,
                    number=number if number > 0 else None,
                )
                return _truncate_git_output(content)
            except Exception as exc:
                return f"ERROR: unable to fetch PR/MR context for '{repo.full_name}': {exc}"

        repo_fetch_pr_context.__doc__ = pr_context_doc
        tools.append(repo_fetch_pr_context)

        if allow_write and binding.can_push:
            commit_doc = (
                f"Commit and push local changes for '{repo.full_name}' on a dedicated branch. "
                "Never use main/master. The branch must already exist or be created with the bound branch tool."
            )

            @tool(f"repo_commit_push__{repo_key}")
            def repo_commit_and_push_bound(commit_message: str, branch_name: str, folder_name: str = "") -> str:
                """Commit and push local repository changes to the authorized remote provider."""
                try:
                    local_path = ensure_repo_cloned(root, connection, repo, folder_name=folder_name)
                    output = commit_and_push_changes(
                        local_path,
                        connection=connection,
                        repo=repo,
                        commit_message=commit_message,
                        branch_name=branch_name,
                    )
                    store.record_action(connection.id, action="push", success=True)
                    return _truncate_git_output(output)
                except Exception as exc:
                    store.record_action(connection.id, action="push", success=False, error=str(exc))
                    return f"ERROR: unable to commit/push changes for '{repo.full_name}': {exc}"

            repo_commit_and_push_bound.__doc__ = commit_doc
            tools.append(repo_commit_and_push_bound)

        if allow_write and binding.can_open_pr:
            pr_doc = (
                f"Open a pull request or merge request for '{repo.full_name}' on {provider_name}. "
                f"Source branch must not be main/master. Target branch defaults to {repo.default_branch}."
            )

            @tool(f"repo_open_pr__{repo_key}")
            def repo_open_pr_or_mr_bound(
                title: str,
                source_branch: str,
                body: str = "",
                target_branch: str = "",
            ) -> str:
                """Create a pull request or merge request for the authorized repository."""
                try:
                    output = create_pull_request(
                        connection,
                        repo=repo,
                        title=title,
                        body=body,
                        source_branch=source_branch,
                        target_branch=target_branch or repo.default_branch,
                    )
                    store.record_action(connection.id, action="pull_request", success=True)
                    return _truncate_git_output(output)
                except Exception as exc:
                    store.record_action(connection.id, action="pull_request", success=False, error=str(exc))
                    return f"ERROR: unable to create PR/MR for '{repo.full_name}': {exc}"

            repo_open_pr_or_mr_bound.__doc__ = pr_doc
            tools.append(repo_open_pr_or_mr_bound)

    return tools


def get_tools_for_agent(
    tool_names: list[str],
    workspace_path: Optional[str] = None,
    git_bindings: list[AgentGitBinding] | None = None,
    mcp_tool_bindings: list[AgentMcpToolBinding] | None = None,
    allow_git_write: bool = False,
) -> list:
    """
    Build tool list for a specific agent.
    Global tools are cached; workspace-scoped tools are built fresh per agent.
    """
    tools = []

    for name in tool_names:
        tool_obj = None

        if name in WORKSPACE_TOOL_BUILDERS:
            # Always build fresh with the agent's workspace path
            try:
                tool_obj = WORKSPACE_TOOL_BUILDERS[name](workspace_path)
            except Exception as e:
                logger.error(f"Failed to build workspace tool '{name}': {e}")
                raise

        elif name in GLOBAL_TOOL_BUILDERS:
            if name not in _global_tool_cache:
                try:
                    _global_tool_cache[name] = GLOBAL_TOOL_BUILDERS[name]()
                except Exception as e:
                    logger.error(f"Failed to build global tool '{name}': {e}")
                    _global_tool_cache[name] = None
            tool_obj = _global_tool_cache.get(name)

        else:
            logger.warning(f"Unknown tool: '{name}'")

        if tool_obj is not None:
            tools.append(tool_obj)

    tools.extend(build_git_tools_for_agent(git_bindings, workspace_path, allow_write=allow_git_write))
    tools.extend(build_mcp_tools_for_agent(mcp_tool_bindings))
    return tools
